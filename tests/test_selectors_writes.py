# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0
#
# AI Disclosure: This file was largely AI-generated. The AI-generated
# portions are made available under CC0-1.0 and not subject to the
# project's licence. The human contributor has reviewed and verified
# that the code is correct.
#
# SPDX-License-Identifier: EPL-2.0 AND CC0-1.0
# Assisted-by: Anthropic Claude Opus 5.5 (claude-opus-5-5)
import json

import httpx
import pytest
import respx

from dittoctl.core.bulk import Category
from dittoctl.core.client import DittoClient
from dittoctl.core.conditions import Conditions, IfEqual
from dittoctl.core.jsonops import json_equal
from dittoctl.core.selectors import Selection, read_ids, resolve
from dittoctl.core.writes import array_operation, merge_operation, message_operation, put_operation
from dittoctl.errors import DittoctlError, DittoError

BASE = "http://ditto.test"
THING = f"{BASE}/api/2/things/org.example:a"


@pytest.fixture
def client():
    with DittoClient(BASE, sleep=lambda _s: None) as c:
        yield c


def test_read_ids_takes_first_column():
    lines = ["﻿# comment", "org.example:a", "  org.example:b\t404\tthings:thing.notfound", "", "org.example:c,x"]
    assert read_ids(lines) == ["org.example:a", "org.example:b", "org.example:c"]


def test_resolve_ids_and_files(client, tmp_path):
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("org.example:b\norg.example:c\norg.example:a\n")
    exclude = tmp_path / "exclude.txt"
    exclude.write_text("org.example:c\n")
    selection = Selection(ids=["org.example:a"], ids_file=str(ids_file), exclude_file=str(exclude))
    assert resolve(client, selection) == ["org.example:a", "org.example:b"]


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        (Selection(), "no things selected"),
        (Selection(ids=["a:1"], rql_filter="exists(attributes/x)"), "either by id"),
    ],
)
def test_resolve_rejects_ambiguous_selections(client, selection, message):
    with pytest.raises(DittoctlError, match=message):
        resolve(client, selection)


@respx.mock
def test_resolve_falls_back_to_paging_when_sse_stream_is_short(client):
    def search(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Accept") == "text/event-stream":
            return httpx.Response(200, content=b'id:a:1\ndata:{"thingId":"a:1"}\n\n')  # ends early
        return httpx.Response(200, json={"items": [{"thingId": "a:1"}, {"thingId": "a:2"}]})

    respx.get(f"{BASE}/api/2/search/things").mock(side_effect=search)
    respx.get(f"{BASE}/api/2/search/things/count").mock(return_value=httpx.Response(200, json=2))
    warnings = []
    ids = resolve(client, Selection(rql_filter="exists(attributes/x)"), warn=warnings.append)
    assert ids == ["a:1", "a:2"]
    assert "returned 1 of 2" in warnings[0]


@respx.mock
def test_merge_operation(client):
    route = respx.patch(f"{THING}/attributes").mock(return_value=httpx.Response(204))
    conditions = Conditions(if_equal=IfEqual.SKIP)
    outcome = merge_operation(client, "attributes", {"room": "lab"}, conditions)("org.example:a")
    assert outcome.category == Category.OK
    assert route.calls.last.request.headers["If-Equal"] == "skip"
    assert json.loads(route.calls.last.request.content) == {"room": "lab"}

    planned = merge_operation(client, "attributes", {"room": "lab"}, conditions, dry_run=True)("org.example:a")
    assert planned.category == Category.PLANNED
    assert planned.detail == {
        "method": "PATCH",
        "path": "/api/2/things/org.example:a/attributes",
        "body": {"room": "lab"},
        "headers": {"If-Equal": "skip"},
    }
    assert route.call_count == 1


@respx.mock
def test_put_operation_create_only_reports_existing(client):
    respx.put(THING).mock(
        return_value=httpx.Response(412, json={"status": 412, "error": "things:precondition.failed", "message": "x"})
    )
    things = {"org.example:a": {"thingId": "org.example:a"}}
    outcome = put_operation(client, things, Conditions(if_none_match="*"))("org.example:a")
    assert outcome.category == Category.EXISTS


@respx.mock
def test_array_add_creates_missing_array_with_if_none_match(client):
    respx.get(f"{THING}/attributes/tags").mock(
        return_value=httpx.Response(404, json={"status": 404, "error": "things:attribute.notfound"})
    )
    put = respx.put(f"{THING}/attributes/tags").mock(return_value=httpx.Response(201))
    outcome = array_operation(client, "attributes/tags", ["x"])("org.example:a")
    assert outcome.category == Category.OK
    assert put.calls.last.request.headers["If-None-Match"] == "*"
    assert json.loads(put.calls.last.request.content) == ["x"]


@respx.mock
def test_array_add_retries_after_concurrent_change(client):
    respx.get(f"{THING}/attributes/tags").mock(
        side_effect=[
            httpx.Response(200, json=["a"], headers={"ETag": 'W/"hash:1"'}),
            httpx.Response(200, json=["a", "z"], headers={"ETag": '"hash:2"'}),
        ]
    )
    put = respx.put(f"{THING}/attributes/tags").mock(
        side_effect=[
            httpx.Response(412, json={"status": 412, "error": "things:precondition.failed", "message": "if-match"}),
            httpx.Response(204),
        ]
    )
    outcome = array_operation(client, "attributes/tags", ["b"], as_set=True)("org.example:a")
    assert outcome.category == Category.OK
    assert [c.request.headers["If-Match"] for c in put.calls] == ['"hash:1"', '"hash:2"']
    assert json.loads(put.calls.last.request.content) == ["a", "z", "b"]


@respx.mock
def test_array_conflict_after_retries(client):
    respx.get(f"{THING}/attributes/tags").mock(return_value=httpx.Response(200, json=[], headers={"ETag": '"hash:1"'}))
    respx.put(f"{THING}/attributes/tags").mock(
        return_value=httpx.Response(412, json={"status": 412, "error": "things:precondition.failed"})
    )
    outcome = array_operation(client, "attributes/tags", ["b"], conflict_retries=2)("org.example:a")
    assert outcome.category == Category.CONFLICT


@respx.mock
def test_array_unchanged_is_not_written(client):
    respx.get(f"{THING}/attributes/tags").mock(return_value=httpx.Response(200, json=["a", 1.0]))
    put = respx.put(f"{THING}/attributes/tags").mock(return_value=httpx.Response(204))
    assert (
        array_operation(client, "attributes/tags", ["a"], as_set=True)("org.example:a").category == Category.UNCHANGED
    )
    assert (
        array_operation(client, "attributes/tags", ["x"], remove=True)("org.example:a").category == Category.UNCHANGED
    )
    # with json equality 1 and 1.0 differ, so nothing matches and nothing is removed either
    removal = array_operation(client, "attributes/tags", [1], remove=True, equal=json_equal)("org.example:a")
    assert removal.category == Category.UNCHANGED
    assert put.call_count == 0


@respx.mock
def test_array_on_non_array_fails(client):
    respx.get(f"{THING}/attributes/tags").mock(return_value=httpx.Response(200, json={"not": "an array"}))
    with pytest.raises(DittoctlError, match="not an array"):
        array_operation(client, "attributes/tags", ["x"])("org.example:a")


@respx.mock
def test_message_operation(client):
    route = respx.post(f"{THING}/features/lamp/outbox/messages/switched").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    outcome = message_operation(client, "switched", {"on": True}, feature="lamp", outbox=True, timeout=5)(
        "org.example:a"
    )
    assert outcome.detail == {"ok": True}
    assert route.calls.last.request.url.params["timeout"] == "5"

    text = respx.post(f"{THING}/inbox/messages/say").mock(return_value=httpx.Response(202))
    message_operation(client, "say", "hello", content_type="text/plain", timeout=0)("org.example:a")
    assert text.calls.last.request.content == b"hello"
    assert text.calls.last.request.headers["Content-Type"] == "text/plain"


@respx.mock
def test_errors_propagate_for_classification(client):
    respx.patch(f"{THING}/attributes").mock(
        return_value=httpx.Response(404, json={"status": 404, "error": "things:thing.notfound"})
    )
    with pytest.raises(DittoError):
        merge_operation(client, "attributes", {}, Conditions())("org.example:a")

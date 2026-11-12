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
import re
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from dittoctl.core.client import DittoClient
from dittoctl.core.search import (
    POST_THRESHOLD,
    Transport,
    count_things,
    find_things,
    search_things,
    sort_option,
    stream_things,
)
from dittoctl.core.sse import SseEvent, iter_sse
from dittoctl.core.things import get_thing, get_things, thing_path, watch_things
from dittoctl.errors import DittoctlError, DittoError

BASE = "http://ditto.test"


def paged_search(total: int):
    """A fake search endpoint serving ``total`` things in pages of the requested size, with cursors."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST":
            params = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        option = params["option"]
        size = int(re.search(r"size\((\d+)\)", option).group(1))
        cursor = re.search(r"cursor\((\d+)\)", option)
        start = int(cursor.group(1)) if cursor else 0
        items = [{"thingId": f"org.example:t{i}"} for i in range(start, min(start + size, total))]
        body = {"items": items}
        if start + size < total:
            body["cursor"] = str(start + size)
        return httpx.Response(200, json=body)

    return handler


@pytest.fixture
def client():
    with DittoClient(BASE) as c:
        yield c


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (None, None),
        ("-_modified", "sort(-_modified)"),
        ("attributes/name,-_modified", "sort(+attributes/name,-_modified)"),
        (["+a", "b"], "sort(+a,+b)"),
        (" , ", None),
    ],
)
def test_sort_option(sort, expected):
    assert sort_option(sort) == expected


@respx.mock
def test_search_follows_cursor_through_all_pages(client):
    route = respx.get(f"{BASE}/api/2/search/things").mock(side_effect=paged_search(450))
    items = list(search_things(client, rql_filter='eq(a,"b")', namespaces=["ns1", "ns2"], fields="thingId"))
    assert len(items) == 450
    assert items[-1] == {"thingId": "org.example:t449"}
    assert route.call_count == 3
    first, last = route.calls[0].request.url.params, route.calls[-1].request.url.params
    assert first["filter"] == 'eq(a,"b")'
    assert first["namespaces"] == "ns1,ns2"
    assert first["fields"] == "thingId"
    assert first["option"] == "size(200)"
    assert last["option"] == "size(200),cursor(400)"


@respx.mock
def test_search_limit_stops_early_and_shrinks_page_size(client):
    route = respx.get(f"{BASE}/api/2/search/things").mock(side_effect=paged_search(1000))
    items = list(search_things(client, limit=50, sort="-_modified"))
    assert len(items) == 50
    assert route.call_count == 1
    assert route.calls.last.request.url.params["option"] == "size(50),sort(-_modified)"


@respx.mock
def test_search_is_lazy(client):
    route = respx.get(f"{BASE}/api/2/search/things").mock(side_effect=paged_search(1000))
    iterator = search_things(client)
    next(iterator)
    assert route.call_count == 1


@respx.mock
def test_long_filters_use_form_post(client):
    route = respx.post(f"{BASE}/api/2/search/things").mock(side_effect=paged_search(5))
    long_filter = "in(thingId," + ",".join(f'"org.example:t{i}"' for i in range(POST_THRESHOLD // 10)) + ")"
    assert len(list(search_things(client, rql_filter=long_filter))) == 5
    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode())["filter"] == [long_filter]


def test_page_size_is_validated(client):
    with pytest.raises(DittoctlError, match="page size"):
        list(search_things(client, page_size=201))


@respx.mock
def test_count(client):
    route = respx.get(f"{BASE}/api/2/search/things/count").mock(return_value=httpx.Response(200, json=42))
    assert count_things(client, rql_filter="exists(attributes/x)", namespaces=["a"]) == 42
    assert route.calls.last.request.url.params["namespaces"] == "a"


@pytest.mark.parametrize(
    ("thing_id", "path", "expected"),
    [
        ("org.example:a", None, "/api/2/things/org.example:a"),
        ("org.example:a", "/", "/api/2/things/org.example:a"),
        ("org.example:a b#c", None, "/api/2/things/org.example:a%20b%23c"),
        ("org.example:a", "/attributes/location/", "/api/2/things/org.example:a/attributes/location"),
        ("org.example:a", "features/my feature", "/api/2/things/org.example:a/features/my%20feature"),
    ],
)
def test_thing_path(thing_id, path, expected):
    assert thing_path(thing_id, path) == expected


@respx.mock
def test_get_thing_sends_historical_headers(client):
    route = respx.get(f"{BASE}/api/2/things/org.example:a").mock(return_value=httpx.Response(200, json={}))
    get_thing(client, "org.example:a", fields="thingId", at_revision=7, at_timestamp="2026-11-01T00:00:00Z")
    request = route.calls.last.request
    assert request.headers["at-historical-revision"] == "7"
    assert request.headers["at-historical-timestamp"] == "2026-11-01T00:00:00Z"
    assert request.url.params["fields"] == "thingId"


@respx.mock
def test_get_things_batches_ids(client):
    def handler(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["ids"].split(",")
        return httpx.Response(200, json=[{"thingId": i} for i in ids if not i.endswith("missing")])

    route = respx.get(f"{BASE}/api/2/things").mock(side_effect=handler)
    ids = [f"org.example:thing-with-a-long-name-{i:04d}" for i in range(100)] + ["org.example:missing"]
    result = list(get_things(client, ids, fields="thingId"))
    assert len(result) == 100
    assert route.call_count > 1
    assert all(len(c.request.url.params["ids"]) <= 1500 for c in route.calls)


def test_sse_parser():
    lines = [
        ": keep-alive",
        "id: 1",
        'data: {"a":',
        "data: 1}",
        "",
        "event: custom",
        "data: x",
        "",
        "data:",
        "",
        "data: last",
    ]
    assert list(iter_sse(lines)) == [
        SseEvent('{"a":\n1}', None, "1"),
        # the last event id carries over until a new one arrives (SSE spec "last event ID buffer")
        SseEvent("x", "custom", "1"),
        SseEvent("", None, "1"),
        SseEvent("last", None, "1"),
    ]


@respx.mock
def test_watch_things_streams_events(client):
    stream = (
        b'data: {"thingId":"org.example:a","attributes":{"x":1}}\n\n:\n\ndata:\n\ndata: {"thingId":"org.example:b"}\n\n'
    )
    route = respx.get(f"{BASE}/api/2/things").mock(
        return_value=httpx.Response(200, content=stream, headers={"Content-Type": "text/event-stream"})
    )
    events = list(watch_things(client, rql_filter="exists(attributes/x)", namespaces=["org.example"],
                               thing_ids=["org.example:a"], fields="thingId", extra_fields="attributes"))  # fmt: skip
    assert events == [{"thingId": "org.example:a", "attributes": {"x": 1}}, {"thingId": "org.example:b"}]
    request = route.calls.last.request
    assert request.headers["Accept"] == "text/event-stream"
    assert dict(request.url.params) == {
        "filter": "exists(attributes/x)",
        "namespaces": "org.example",
        "ids": "org.example:a",
        "fields": "thingId",
        "extraFields": "attributes",
    }


@respx.mock
def test_watch_reports_errors(client):
    respx.get(f"{BASE}/api/2/things").mock(
        return_value=httpx.Response(403, json={"status": 403, "error": "things:thing.notallowed", "message": "no"})
    )
    with pytest.raises(DittoctlError, match=r"403 things:thing\.notallowed"):
        list(watch_things(client))


class BrokenStream(httpx.SyncByteStream):
    """Delivers the given bytes, then fails like a dropped connection."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self):
        yield self.data
        raise httpx.ReadError("connection reset")


def sse_body(*things: dict) -> bytes:
    return b"".join(f"id:{t['thingId']}\ndata:{json.dumps(t)}\n\n".encode() for t in things)


@pytest.fixture
def no_sleep_client():
    with DittoClient(BASE, sleep=lambda _s: None) as c:
        yield c


@respx.mock
def test_stream_things(client):
    route = respx.get(f"{BASE}/api/2/search/things").mock(
        return_value=httpx.Response(200, content=sse_body({"thingId": "a:1"}, {"thingId": "a:2"}) + b":\n\n")
    )
    items = list(stream_things(client, rql_filter="exists(attributes/x)", namespaces=["a"], fields="thingId",
                               sort="-_modified"))  # fmt: skip
    assert items == [{"thingId": "a:1"}, {"thingId": "a:2"}]
    request = route.calls.last.request
    assert request.headers["Accept"] == "text/event-stream"
    assert dict(request.url.params) == {
        "filter": "exists(attributes/x)",
        "namespaces": "a",
        "fields": "thingId",
        "option": "sort(-_modified)",
    }


@respx.mock
def test_stream_things_limit(client):
    respx.get(f"{BASE}/api/2/search/things").mock(
        return_value=httpx.Response(200, content=sse_body(*({"thingId": f"a:{i}"} for i in range(10))))
    )
    assert len(list(stream_things(client, limit=3))) == 3


@respx.mock
def test_stream_things_raises_error_events(client):
    error = {"status": 400, "error": "rql.expression.invalid", "message": "Unknown property name: features"}
    respx.get(f"{BASE}/api/2/search/things").mock(
        return_value=httpx.Response(
            200, content=sse_body({"thingId": "a:1"}) + f"data:{json.dumps(error)}\n\n".encode()
        )
    )
    stream = stream_things(client)
    assert next(stream) == {"thingId": "a:1"}
    with pytest.raises(DittoError) as info:
        next(stream)
    assert info.value.status == 400
    assert info.value.error == "rql.expression.invalid"


@respx.mock
def test_stream_things_resumes_after_dropped_connection(no_sleep_client):
    route = respx.get(f"{BASE}/api/2/search/things").mock(
        side_effect=[
            httpx.Response(200, stream=BrokenStream(sse_body({"thingId": "a:1"}, {"thingId": "a:2"}))),
            httpx.Response(200, content=sse_body({"thingId": "a:3"})),
        ]
    )
    assert [t["thingId"] for t in stream_things(no_sleep_client)] == ["a:1", "a:2", "a:3"]
    assert "Last-Event-ID" not in route.calls[0].request.headers
    assert route.calls[1].request.headers["Last-Event-ID"] == "a:2"


@respx.mock
def test_stream_things_gives_up_after_max_reconnects(no_sleep_client):
    respx.get(f"{BASE}/api/2/search/things").mock(side_effect=lambda _r: httpx.Response(200, stream=BrokenStream(b"")))
    with pytest.raises(DittoctlError, match="after 3 reconnects"):
        list(stream_things(no_sleep_client))


@pytest.mark.parametrize(
    ("fields", "transport", "allowed", "rql_filter", "expected"),
    [
        ("thingId", Transport.AUTO, True, None, "sse"),
        (" thingId ", Transport.AUTO, True, None, "sse"),
        ("thingId,attributes", Transport.AUTO, True, None, "paging"),
        (None, Transport.AUTO, True, None, "paging"),
        ("thingId", Transport.AUTO, False, None, "paging"),
        ("thingId", Transport.AUTO, True, "in(thingId," + ",".join(['"a:1"'] * 500) + ")", "paging"),
        ("thingId,attributes", Transport.SSE, False, None, "sse"),
        ("thingId", Transport.PAGING, True, None, "paging"),
    ],
)
@respx.mock
def test_find_things_picks_transport(client, fields, transport, allowed, rql_filter, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Accept") == "text/event-stream":
            return httpx.Response(200, content=sse_body({"thingId": "via:sse"}))
        return httpx.Response(200, json={"items": [{"thingId": "via:paging"}]})

    respx.route(host="ditto.test").mock(side_effect=handler)
    items = list(find_things(client, rql_filter=rql_filter, fields=fields, transport=transport,
                             streaming_allowed=allowed))  # fmt: skip
    assert items == [{"thingId": f"via:{expected}"}]

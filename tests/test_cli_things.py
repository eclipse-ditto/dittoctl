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

from dittoctl.errors import ExitCode

URL = "http://ditto.test"
SEARCH = f"{URL}/api/2/search/things"
THINGS = [
    {"thingId": "org.example:a", "attributes": {"room": "lab"}, "_modified": "2026-11-06T10:00:00Z"},
    {"thingId": "org.example:b", "attributes": {"room": "office", "floor": 2}, "_modified": "2026-11-06T11:00:00Z"},
]


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        mock.get("/api/2/search/things").mock(return_value=httpx.Response(200, json={"items": THINGS}))
        mock.get("/api/2/search/things/count").mock(return_value=httpx.Response(200, json=2))
        yield mock


def test_search_ndjson_with_filter_namespaces_fields(run, ditto):
    result = run(
        "--url", URL, "things", "search",
        "-f", 'eq( attributes/room , "lab" )', "-n", "org.example,other", "--fields", "thingId,attributes",
        "-o", "ndjson",
    )  # fmt: skip
    assert result.exit_code == 0, result.stderr
    assert [json.loads(line) for line in result.stdout.splitlines()] == THINGS
    params = ditto.calls.last.request.url.params
    assert params["filter"] == 'eq(attributes/room,"lab")'  # normalized before sending
    assert params["namespaces"] == "org.example,other"
    assert params["fields"] == "thingId,attributes"


def test_search_defaults_to_ndjson_when_piped(run, ditto):
    result = run("--url", URL, "things", "search")
    assert result.stdout.splitlines()[0].startswith('{"thingId":"org.example:a"')


def test_search_uses_context_namespaces(run, ditto):
    assert run("config", "add-context", "c", "--url", URL, "--namespace", "org.example").exit_code == 0
    run("things", "search", "-o", "ids")
    assert ditto.calls.last.request.url.params["namespaces"] == "org.example"


def test_search_csv_and_ids(run, ditto):
    csv_result = run("--url", URL, "things", "search", "-o", "csv", "--short-headers", "--excel")
    lines = csv_result.stdout.splitlines()
    assert lines[0] == "﻿thingId,room,_modified,floor"
    assert lines[1] == "org.example:a,lab,2026-11-06 10:00:00,"
    assert run("--url", URL, "things", "search", "-o", "ids", "--transport", "paging").stdout == (
        "org.example:a\norg.example:b\n"
    )


def sse_stream(*ids: str) -> bytes:
    return b"".join(f'id:{i}\ndata:{{"thingId":"{i}"}}\n\n'.encode() for i in ids)


def test_search_ids_streams_via_sse(run):
    with respx.mock(base_url=URL) as mock:
        route = mock.get("/api/2/search/things", headers={"Accept": "text/event-stream"}).mock(
            return_value=httpx.Response(200, content=sse_stream("org.example:a", "org.example:b"))
        )
        result = run("--url", URL, "things", "search", "-n", "org.example", "-o", "ids")
    assert result.stdout == "org.example:a\norg.example:b\n"
    assert route.calls.last.request.url.params["fields"] == "thingId"


def test_context_can_turn_off_search_streaming(run, ditto):
    assert run("config", "add-context", "c", "--url", URL, "--no-search-streaming").exit_code == 0
    assert "search-streaming = false" in run("config", "view", "c").stdout
    run("things", "search", "-o", "ids")
    request = ditto.calls.last.request
    assert request.headers.get("Accept") != "text/event-stream"
    assert request.url.params["option"] == "size(200)"


def test_export_with_explicit_sse_transport(run, tmp_path):
    with respx.mock(base_url=URL) as mock:
        mock.get("/api/2/search/things", headers={"Accept": "text/event-stream"}).mock(
            return_value=httpx.Response(200, content=sse_stream("org.example:a"))
        )
        target = tmp_path / "out.ndjson"
        result = run("--url", URL, "things", "export", "--transport", "sse", "-o", "ndjson", "--out", str(target))
    assert result.exit_code == 0, result.stderr
    assert target.read_text() == '{"thingId":"org.example:a"}\n'


def test_search_table(run, ditto):
    result = run("--url", URL, "things", "search", "-o", "table", "--columns", "thingId,attributes/room")
    lines = result.stdout.splitlines()
    assert lines[0].split() == ["thingId", "attributes/room"]
    assert lines[2].split() == ["org.example:b", "office"]


def test_invalid_filter_is_rejected_before_sending(run, ditto):
    result = run("--url", URL, "things", "search", "-f", "eq(attributes/room,lab)")
    assert result.exit_code == ExitCode.ERROR
    assert "expected a value" in result.stderr
    assert "^" in result.stderr
    assert not ditto.calls


def test_no_validate_sends_filter_as_is(run, ditto):
    run("--url", URL, "things", "count", "-f", "eq(a,b)", "--no-validate")
    assert ditto.calls.last.request.url.params["filter"] == "eq(a,b)"


def test_filter_from_file(run, ditto, tmp_path):
    rql_file = tmp_path / "filter.rql"
    rql_file.write_text("and(\n  exists(attributes/room),\n  eq(attributes/floor, 2)\n)\n", encoding="utf-8")
    result = run("--url", URL, "things", "count", "-f", f"@{rql_file}")
    assert result.stdout.strip() == "2"
    assert ditto.calls.last.request.url.params["filter"] == "and(exists(attributes/room),eq(attributes/floor,2))"


def test_export_to_file(run, ditto, tmp_path):
    target = tmp_path / "out.csv"
    result = run("--url", URL, "things", "export", "--fields", "thingId,attributes", "--out", str(target), "--excel")
    assert result.exit_code == 0, result.stderr
    assert "Exported 2 things" in result.stderr
    assert target.read_bytes().startswith(b"\xef\xbb\xbfthingId,attributes/room")


def test_get_single_and_path(run):
    with respx.mock(base_url=URL) as mock:
        route = mock.get("/api/2/things/org.example:a/attributes/room").mock(
            return_value=httpx.Response(200, json="lab")
        )
        result = run("--url", URL, "things", "get", "org.example:a", "--path", "attributes/room", "--at-revision", "3")
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == "lab"
    assert route.calls.last.request.headers["at-historical-revision"] == "3"


def test_get_not_modified(run):
    with respx.mock(base_url=URL) as mock:
        route = mock.get("/api/2/things/org.example:a").mock(return_value=httpx.Response(304))
        result = run("--url", URL, "things", "get", "org.example:a", "--if-none-match", 'W/"rev:3"')
    assert result.exit_code == 0
    assert "Not modified" in result.stderr
    assert route.calls.last.request.headers["If-None-Match"] == '"rev:3"'


def test_get_several_warns_about_missing(run):
    with respx.mock(base_url=URL) as mock:
        mock.get("/api/2/things").mock(return_value=httpx.Response(200, json=[THINGS[0]]))
        result = run("--url", URL, "things", "get", "org.example:a", "org.example:missing", "-o", "ndjson")
    assert json.loads(result.stdout) == THINGS[0]
    assert "1 of 2 things were not found" in result.stderr


def test_get_several_rejects_single_thing_options(run):
    result = run("--url", URL, "things", "get", "a:1", "a:2", "--path", "attributes")
    assert result.exit_code == ExitCode.ERROR
    assert "single thing id" in result.stderr


def test_watch(run):
    stream = b'data: {"thingId":"org.example:a","attributes":{"room":"lab"}}\n\n'
    with respx.mock(base_url=URL) as mock:
        mock.get("/api/2/things").mock(return_value=httpx.Response(200, content=stream))
        result = run("--url", URL, "things", "watch", "-n", "org.example")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"thingId": "org.example:a", "attributes": {"room": "lab"}}


def test_rql_lint_and_fmt(run):
    assert run("rql", "lint", 'eq(a,"b")').exit_code == 0
    bad = run("rql", "lint", "and(eq(a,1),)")
    assert bad.exit_code == ExitCode.CHECK_FAILED
    assert "expected an operator" in bad.stderr
    assert run("rql", "fmt", "or( eq(a,1), exists(b) )").stdout == "or(\n  eq(a,1),\n  exists(b)\n)\n"
    assert run("rql", "fmt", "--compact", "@-", stdin="or(\n eq(a,1)\n)").stdout == "or(eq(a,1))\n"

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
"""Agent mode, protected contexts, bounded output and the other features for use by LLM agents."""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest
import respx

from dittoctl.core import rql
from dittoctl.core.fields import field_stats, json_type
from dittoctl.core.jsonops import json_diff
from dittoctl.core.streams import Limited, Timeboxed
from dittoctl.errors import ExitCode
from test_search_things import paged_search

URL = "http://ditto.test"
A = "org.example:a"
B = "org.example:b"


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")


# --- agent mode -------------------------------------------------------------------------------


def test_agent_mode_is_detected_and_can_be_switched_off(run, ditto, monkeypatch):
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, json={"thingId": A, "attributes": {}}))
    assert run("--url", URL, "things", "get", A).stdout.count("\n") > 1  # indented
    monkeypatch.setenv("AI_AGENT", "some-agent")
    assert run("--url", URL, "things", "get", A).stdout == '{"thingId":"org.example:a","attributes":{}}\n'
    assert run("--url", URL, "--no-agent", "things", "get", A).stdout.count("\n") > 1
    monkeypatch.delenv("AI_AGENT")
    assert run("--url", URL, "--agent", "things", "get", A).stdout.count("\n") == 1


def test_agent_errors_are_json(run, ditto, agent):
    ditto.get(f"/api/2/things/{A}").mock(
        return_value=httpx.Response(
            404,
            json={"status": 404, "error": "things:thing.notfound", "message": "not found", "description": "Check it."},
            headers={"correlation-id": "c-1"},
        )
    )
    result = run("--url", URL, "things", "get", A)
    assert result.exit_code == ExitCode.NOT_FOUND
    assert json.loads(result.stderr) == {
        "exitCode": 4,
        "message": "not found",
        "status": 404,
        "error": "things:thing.notfound",
        "description": "Check it.",
        "correlationId": "c-1",
    }
    usage = json.loads(run("--url", URL, "things", "get").stderr)
    assert usage["exitCode"] == 1
    assert usage["error"] == "usage"
    assert "dittoctl things get [OPTIONS] THING_ID..." in usage["usage"]


# --- bounded output ---------------------------------------------------------------------------


def test_agents_get_a_limited_search_result(run, ditto, agent):
    ditto.get("/api/2/search/things").mock(side_effect=paged_search(120))
    result = run("--url", URL, "things", "search", "--fields", "thingId,attributes")
    assert result.stdout.count("\n") == 50
    assert "Showing the first 50 things; there are more" in result.stderr
    assert run("--url", URL, "things", "search", "--fields", "thingId,attributes", "--all").stdout.count("\n") == 120
    limited = run("--url", URL, "things", "search", "--fields", "thingId,attributes", "--limit", "70")
    assert limited.stdout.count("\n") == 70
    assert "there are more" not in limited.stderr


def test_search_is_not_limited_without_agent(run, ditto):
    ditto.get("/api/2/search/things").mock(side_effect=paged_search(120))
    assert run("--url", URL, "things", "search", "--fields", "thingId,attributes").stdout.count("\n") == 120


def test_limited_closes_its_source():
    closed = []

    def source():
        try:
            yield from range(10)
        finally:
            closed.append(True)

    limited = Limited(source(), 3)
    assert list(limited) == [0, 1, 2]
    assert limited.more
    assert closed == [True]
    exact = Limited(iter(range(3)), 3)
    assert list(exact) == [0, 1, 2]
    assert not exact.more


def test_timeboxed_stops_a_blocking_stream():
    release = threading.Event()

    def stream():
        yield 1
        release.wait(5)  # blocks like an SSE stream without events
        yield 2

    started = time.monotonic()
    boxed = Timeboxed(stream(), duration=0.2)
    assert list(boxed) == [1]
    assert boxed.stopped == "duration"
    assert time.monotonic() - started < 2
    release.set()


def test_timeboxed_max_items_and_errors():
    boxed = Timeboxed(iter(range(10)), max_items=2)
    assert list(boxed) == [0, 1]
    assert boxed.stopped == "max-items"
    timed = Timeboxed(iter(range(10)), duration=5, max_items=3)
    assert list(timed) == [0, 1, 2]
    assert timed.stopped == "max-items"

    def failing():
        yield 1
        raise ValueError("broken stream")

    with pytest.raises(ValueError, match="broken stream"):
        list(Timeboxed(failing(), duration=5))


def test_watch_max_events_and_explicit_ids_ignore_context_namespaces(run, ditto):
    assert run("config", "add-context", "dev", "--url", URL, "--namespace", "other").exit_code == 0
    stream = b"".join(f'data: {{"thingId":"{A}","attributes":{{"n":{i}}}}}\n\n'.encode() for i in range(3))
    route = ditto.get("/api/2/things").mock(return_value=httpx.Response(200, content=stream))
    result = run("things", "watch", "--ids", A, "--max-events", "2")
    assert result.exit_code == 0
    assert result.stdout.count("\n") == 2
    assert "namespaces" not in route.calls.last.request.url.params
    run("things", "watch", "--max-events", "1")
    assert route.calls.last.request.url.params["namespaces"] == "other"


def test_history_limit(run, ditto, agent):
    stream = b"".join(f'data: {{"thingId":"{A}","_revision":{i}}}\n\n'.encode() for i in range(60))
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, content=stream))
    result = run("--url", URL, "things", "history", A, "--from-revision", "1")
    assert result.stdout.count("\n") == 50
    assert "there are more" in result.stderr
    assert run("--url", URL, "things", "history", A, "--from-revision", "1", "--limit", "5").stdout.count("\n") == 5


# --- results of bulk writes -------------------------------------------------------------------


def test_results_lines_and_summary(run, ditto, agent):
    ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    ditto.patch(f"/api/2/things/{B}").mock(
        return_value=httpx.Response(
            400,
            json={
                "status": 400,
                "error": "wot:payload.validation.error",
                "message": "not conform",
                "description": "not defined in the model: [x]",
            },
        )
    )
    result = run("--url", URL, "things", "set", "attributes/x", "1", A, B)
    assert result.exit_code == ExitCode.PARTIAL_FAILURE
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert lines[0] == {
        "thingId": B,
        "result": "failed",
        "status": 400,
        "error": "wot:payload.validation.error",
        "message": "not conform",
        "description": "not defined in the model: [x]",
    }
    assert lines[1]["summary"]["counts"] == {"ok": 1, "failed": 1}
    assert lines[1]["summary"]["failures"] == 1
    every = run("--url", URL, "things", "set", "attributes/x", "1", A, B, "--results", "all")
    assert sorted(json.loads(line).get("thingId", "") for line in every.stdout.splitlines()) == ["", A, B]
    assert run("--url", URL, "things", "set", "attributes/x", "1", A, B, "--results", "none").stdout == ""


def test_dry_run_results_show_the_first_planned_requests(run, ditto, agent, tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("\n".join(f"org.example:t{i}" for i in range(10)))
    result = run("--url", URL, "things", "set", "attributes/x", "1", "--ids-file", str(ids), "--dry-run")
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line.get("result") for line in lines] == ["planned"] * 3 + [None]
    assert lines[0]["plan"]["headers"] == {"If-Match": "*", "If-Equal": "skip"}
    assert lines[-1]["summary"]["dryRun"] is True


# --- protected contexts -----------------------------------------------------------------------


def test_single_writes_need_protected_context_confirmation(run, ditto):
    assert run("config", "add-context", "prod", "--url", URL, "--protected").exit_code == 0
    route = ditto.put("/api/2/policies/org.example:p").mock(return_value=httpx.Response(201, json={}))
    refused = run("policies", "put", "org.example:p", "-d", "{}")
    assert refused.exit_code == ExitCode.ABORTED
    assert "--confirm-context prod" in refused.stderr
    assert route.call_count == 0
    assert run("policies", "put", "org.example:p", "-d", "{}", "--confirm-context", "prod").exit_code == 0
    assert route.call_count == 1


def test_api_only_guards_writing_methods(run, ditto):
    assert run("config", "add-context", "prod", "--url", URL, "--protected").exit_code == 0
    ditto.get("/api/2/whoami").mock(return_value=httpx.Response(200, json={}))
    ditto.delete(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    assert run("api", "GET", "/api/2/whoami").exit_code == 0
    assert run("api", "DELETE", f"/api/2/things/{A}").exit_code == ExitCode.ABORTED


def test_agents_dont_write_to_protected_contexts(run, ditto, agent):
    assert run("config", "add-context", "prod", "--url", URL, "--protected").exit_code == 0
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    for args in (("things", "set", "attributes/x", "1", A), ("things", "put", A, "-d", "{}")):
        result = run(*args, "--confirm-context", "prod")
        assert result.exit_code == ExitCode.ABORTED
        assert (
            "doesn't write to protected contexts in agent mode" in json.loads(result.stderr.splitlines()[-1])["message"]
        )
    assert route.call_count == 0
    assert run("things", "set", "attributes/x", "1", A, "--dry-run").exit_code == 0


# --- checks, diff, RQL hints, fields ----------------------------------------------------------


def test_json_diff():
    old = {"thingId": A, "attributes": {"on": False, "color": {"r": 1}, "tags": [1]}}
    new = {"thingId": A, "attributes": {"on": True, "color": {"r": 1}, "room": "lab"}}
    assert json_diff(old, new) == [
        {"op": "replace", "path": "/attributes/on", "old": False, "new": True},
        {"op": "add", "path": "/attributes/room", "new": "lab"},
        {"op": "remove", "path": "/attributes/tags", "old": [1]},
    ]
    assert json_diff(old, old) == []
    assert json_diff(1, 2) == [{"op": "replace", "path": "/", "old": 1, "new": 2}]


def test_diff_as_json(run, ditto, agent, tmp_path):
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, json={"attributes": {"x": 1}}))
    local = tmp_path / "a.json"
    local.write_text(json.dumps({"attributes": {"x": 2}}))
    result = run("--url", URL, "things", "diff", A, "--file", str(local))
    assert result.exit_code == ExitCode.CHECK_FAILED
    assert json.loads(result.stdout) == [{"op": "replace", "path": "/attributes/x", "old": 1, "new": 2}]


def test_rql_warns_about_exists_on_whole_objects(run):
    assert rql.warnings(rql.parse("and(exists(attributes),exists(features/temp))")) == [
        "Ditto rejects exists(attributes) on the whole object (eclipse-ditto/ditto#2637); "
        "use a concrete path such as exists(attributes/<name>)"
    ]
    result = run("rql", "lint", "exists(features)")
    assert result.exit_code == 0
    assert "Ditto rejects exists(features)" in result.stderr


def test_field_stats():
    things = [
        {"thingId": A, "attributes": {"room": "lab", "floor": 1, "tags": ["a", "b", "c", "d"]}},
        {"thingId": B, "attributes": {"room": "lab", "floor": 1.5}, "features": {}},
    ]
    stats, total = field_stats(things)
    by_path = {s.path: s.to_json(total) for s in stats}
    assert total == 2
    assert by_path["attributes/room"] == {
        "path": "attributes/room",
        "types": ["string"],
        "count": 2,
        "share": 1.0,
        "examples": ["lab"],
    }
    assert by_path["attributes/floor"]["types"] == ["integer", "number"]
    assert by_path["attributes/tags"]["examples"] == [["a", "b", "c", "…"]]
    assert by_path["features"]["types"] == ["object"]
    assert json_type([1, "x"]) == "array<integer|string>"


def test_fields_command(run, ditto):
    route = ditto.get("/api/2/search/things").mock(
        return_value=httpx.Response(200, json={"items": [{"thingId": A, "attributes": {"room": "lab"}}]})
    )
    result = run("--url", URL, "things", "fields", "--path", "attributes", "--sample", "10")
    assert [json.loads(line)["path"] for line in result.stdout.splitlines()] == ["attributes/room", "thingId"]
    params = route.calls.last.request.url.params
    assert params["fields"] == "attributes"
    assert "size(10)" in params["option"]


def test_no_agent_holds_for_errors_before_the_command_runs(run, agent):
    assert json.loads(run("thngs").stderr)["message"] == "No such command 'thngs'. Did you mean 'things'?"
    assert run("--no-agent", "thngs").stderr.startswith("Usage: dittoctl")


def test_agent_json_lists_and_failed_checks(run, ditto, agent, tmp_path):
    ditto.get("/api/2/search/things").mock(side_effect=paged_search(3))
    result = run("--url", URL, "things", "search", "--fields", "thingId,attributes", "-o", "json")
    assert result.stdout.count("\n") == 1
    assert len(json.loads(result.stdout)) == 3
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, json={"x": 1}))
    local = tmp_path / "a.json"
    local.write_text('{"x": 2}')
    diff = run("--url", URL, "things", "diff", A, "--file", str(local))
    assert json.loads(diff.stderr.splitlines()[-1]) == {
        "exitCode": 6,
        "message": f"1 difference(s) between {A} and {local}",
    }


def test_connections_create_with_id_uses_put(run, ditto):
    ditto.get("/api/2/connections/c-1").mock(
        side_effect=[
            httpx.Response(404, json={"status": 404, "error": "connectivity:connection.notfound"}),
            httpx.Response(200, json={"id": "c-1"}),
        ]
    )
    put = ditto.put("/api/2/connections/c-1").mock(return_value=httpx.Response(201, json={"id": "c-1"}))
    result = run("--url", URL, "connections", "create", "-d", '{"id":"c-1","connectionType":"http-push"}')
    assert result.exit_code == 0, result.stderr
    assert put.call_count == 1
    exists = run("--url", URL, "connections", "create", "-d", '{"id":"c-1"}')
    assert exists.exit_code == ExitCode.ERROR
    assert "already exists" in exists.stderr


def test_piggyback_error_responses_fail(run, ditto):
    ditto.post("/devops/piggyback/gateway").mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "devops.responses:errorResponse",
                "status": 503,
                "instance": "gw-1",
                "payload": {"status": 503, "error": "ask.error", "message": "Ask timed out"},
            },
        )
    )
    result = run("--url", URL, "devops", "piggyback", "gateway", "-d", '{"targetActorSelection":"/user/x"}')
    assert result.exit_code == ExitCode.ERROR
    assert "1 error response(s), e.g. from gw-1: 503 Ask timed out" in result.stderr

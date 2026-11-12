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

import click
import httpx
import pytest
import respx

from dittoctl.errors import ExitCode

URL = "http://ditto.test"
A = "org.example:a"
B = "org.example:b"


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


def test_patch_with_ids(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}/attributes").mock(return_value=httpx.Response(204))
    ditto.patch(f"/api/2/things/{B}/attributes").mock(return_value=httpx.Response(204))
    result = run("--url", URL, "things", "patch", "attributes", A, B, "-d", '{"room":"lab"}')
    assert result.exit_code == 0, result.stderr
    assert "Patch: 2 of 2 things" in result.stderr
    assert route.calls.last.request.headers["If-Equal"] == "skip"


def test_patch_if_equal_can_be_overridden(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    run("--url", URL, "things", "patch", "/", A, "-d", '{"attributes":{"x":1}}', "--if-equal", "update")
    assert route.calls.last.request.headers["If-Equal"] == "update"


def test_patch_dry_run_writes_nothing(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}/attributes").mock(return_value=httpx.Response(204))
    result = run("--url", URL, "things", "patch", "attributes", A, "-d", '{"room":"lab"}', "--dry-run")
    assert result.exit_code == 0
    assert route.call_count == 0
    assert "Dry run, nothing written" in result.stderr
    assert json.loads(result.stdout)["path"] == f"/api/2/things/{A}/attributes"


def test_patch_refuses_arrays(run):
    result = run("--url", URL, "things", "patch", "attributes", A, "-d", '{"tags":["x"]}')
    assert result.exit_code == ExitCode.ERROR
    assert "replaces arrays as a whole" in result.stderr


def test_max_affected_requires_yes(run, ditto, tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("\n".join(f"org.example:t{i}" for i in range(101)))
    result = run("--url", URL, "things", "set", "attributes/x", "1", "--ids-file", str(ids))
    assert result.exit_code == ExitCode.ABORTED
    assert "more than --max-affected 100" in result.stderr
    assert not ditto.calls


def test_set_parses_json_values(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    for value, expected in (("42", 42), ("lab", "lab"), ('{"a":true}', {"a": True})):
        run("--url", URL, "things", "set", "attributes/location/room", value, A)
        assert json.loads(route.calls.last.request.content) == {"attributes": {"location": {"room": expected}}}
    run("--url", URL, "things", "set", "attributes/serial", "0042", A, "--string")
    assert json.loads(route.calls.last.request.content) == {"attributes": {"serial": "0042"}}


def test_unset_sends_null(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    run("--url", URL, "things", "unset", "attributes/old", A)
    assert json.loads(route.calls.last.request.content) == {"attributes": {"old": None}}


PRECONDITION_FAILED = {
    "status": 412,
    "error": "things:precondition.failed",
    "message": "The comparison of precondition header 'if-match' for the requested Thing resource evaluated to "
    "false. Header value: '*', actual entity-tag: 'null'.",
}


def test_root_merges_never_create_things(run, ditto):
    # Ditto creates a missing thing on a merge at its root; If-Match: * turns that into a failed precondition
    ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    missing = ditto.patch(f"/api/2/things/{B}").mock(return_value=httpx.Response(412, json=PRECONDITION_FAILED))
    for args in (("set", "attributes/x", "1"), ("unset", "attributes/x"), ("patch", "/", "-d", '{"attributes":{}}')):
        result = run("--url", URL, "things", *args, A, B)
        assert result.exit_code == ExitCode.PARTIAL_FAILURE, args
        assert "ok 1, not-found 1" in result.stderr or "not-found 1, ok 1" in result.stderr
        assert missing.calls.last.request.headers["If-Match"] == "*"


def test_root_merge_keeps_unchanged_and_explicit_preconditions(run, ditto):
    route = ditto.patch(f"/api/2/things/{A}").mock(
        return_value=httpx.Response(
            412,
            json={
                "status": 412,
                "error": "things:precondition.failed",
                "message": "The previous value was equal to the new value and the 'if-equal' header was set to 'skip'.",
            },
        )
    )
    result = run("--url", URL, "things", "set", "attributes/x", "1", A)
    assert result.exit_code == 0
    assert "unchanged 1" in result.stderr
    run("--url", URL, "things", "set", "attributes/x", "1", A, "--if-match", "rev:3")
    assert route.calls.last.request.headers["If-Match"] == '"rev:3"'


def test_merges_below_the_root_need_no_precondition(run, ditto):
    # Ditto answers 404 for a missing thing there, and If-Match: * would reject paths that don't exist yet
    route = ditto.patch(f"/api/2/things/{A}/attributes/location").mock(return_value=httpx.Response(204))
    run("--url", URL, "things", "patch", "attributes/location", A, "-d", '{"room":"lab"}')
    assert "If-Match" not in route.calls.last.request.headers


def test_failures_show_dittos_description(run, ditto, tmp_path):
    ditto.patch(f"/api/2/things/{A}").mock(
        return_value=httpx.Response(
            400,
            json={
                "status": 400,
                "error": "wot:payload.validation.error",
                "message": "The provided payload did not conform to the specified WoT model.",
                "description": "The Thing's attributes contained JSON fields which were not defined in the model: [x]",
            },
        )
    )
    failed = tmp_path / "failed.tsv"
    result = run("--url", URL, "things", "set", "attributes/x", "1", A, "--failed-out", str(failed))
    assert "not defined in the model: [x]" in result.stderr
    assert failed.read_text().splitlines()[1].endswith("not defined in the model: [x]")


def test_array_remove_has_no_as_set(run):
    result = run("--url", URL, "things", "array", "remove", "attributes/tags", A, "--items", "[1]", "--as-set")
    assert result.exit_code == ExitCode.ERROR
    assert "No such option" in result.stderr


def test_delete_needs_yes_when_not_interactive(run, ditto):
    route = ditto.delete(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    refused = run("--url", URL, "things", "delete", A)
    assert refused.exit_code == ExitCode.ABORTED
    assert route.call_count == 0
    assert run("--url", URL, "things", "delete", A, "--yes").exit_code == 0
    assert route.call_count == 1


def test_protected_context_needs_confirmation(run, ditto):
    assert run("config", "add-context", "prod", "--url", URL, "--protected").exit_code == 0
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    refused = run("things", "set", "attributes/x", "1", A)
    assert refused.exit_code == ExitCode.ABORTED
    assert "--confirm-context prod" in refused.stderr
    assert run("things", "set", "attributes/x", "1", A, "--confirm-context", "prod").exit_code == 0
    assert route.call_count == 1


def test_failures_exit_2_and_are_listed(run, ditto, tmp_path):
    ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    ditto.patch(f"/api/2/things/{B}").mock(
        return_value=httpx.Response(404, json={"status": 404, "error": "things:thing.notfound", "message": "gone"})
    )
    failed = tmp_path / "failed.tsv"
    result = run("--url", URL, "things", "set", "attributes/x", "1", A, B, "--failed-out", str(failed))
    assert result.exit_code == ExitCode.PARTIAL_FAILURE
    assert "1 of 2 things failed" in result.stderr
    assert failed.read_text().splitlines()[1].split("\t")[:3] == [B, "404", "things:thing.notfound"]


def test_stdin_cannot_be_used_twice(run):
    result = run("--url", URL, "things", "patch", "attributes", "--ids-file", "-", "-d", "@-")
    assert result.exit_code == ExitCode.ERROR
    assert "stdin can't provide both" in result.stderr


def test_import_create_reports_existing_without_failing(run, ditto, tmp_path):
    source = tmp_path / "things.ndjson"
    source.write_text(json.dumps({"thingId": A, "attributes": {}}) + "\n" + json.dumps({"thingId": B}) + "\n")
    ditto.put(f"/api/2/things/{A}").mock(return_value=httpx.Response(201, json={}))
    existing = ditto.put(f"/api/2/things/{B}").mock(
        return_value=httpx.Response(412, json={"status": 412, "error": "things:precondition.failed", "message": "x"})
    )
    result = run("--url", URL, "things", "import", str(source))
    assert result.exit_code == 0, result.stderr
    assert "ok 1" in result.stderr
    assert "exists 1" in result.stderr
    assert existing.calls.last.request.headers["If-None-Match"] == "*"


def test_import_rejects_items_without_thing_id(run, tmp_path):
    source = tmp_path / "things.json"
    source.write_text('[{"thingId": "a:1"}, {"attributes": {}}]')
    result = run("--url", URL, "things", "import", str(source))
    assert result.exit_code == ExitCode.ERROR
    assert "item 2 is not a thing" in result.stderr


def test_verify(run, ditto, tmp_path):
    ditto.get("/api/2/things").mock(
        return_value=httpx.Response(200, json=[
            {"thingId": A, "attributes": {"x": 1.0}},
            {"thingId": B, "attributes": {"x": 2}},
            {"thingId": "org.example:c"},
        ])
    )  # fmt: skip
    failed = tmp_path / "mismatch.tsv"
    result = run("--url", URL, "things", "verify", "attributes/x", A, B, "org.example:c", "org.example:d",
                 "--equals", "1", "--failed-out", str(failed))  # fmt: skip
    assert result.exit_code == ExitCode.CHECK_FAILED
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(line["thingId"], line["result"]) for line in lines] == [
        (B, "mismatch"), ("org.example:c", "missing"), ("org.example:d", "not-found"),
    ]  # fmt: skip
    assert "match 1, mismatch 1, missing 1, not found 1" in result.stderr
    assert len(failed.read_text().splitlines()) == 4


def test_array_add_command(run, ditto):
    ditto.get(f"/api/2/things/{A}/attributes/tags").mock(
        return_value=httpx.Response(200, json=["a"], headers={"ETag": '"hash:1"'})
    )
    put = ditto.put(f"/api/2/things/{A}/attributes/tags").mock(return_value=httpx.Response(204))
    result = run("--url", URL, "things", "array", "add", "attributes/tags", A, "--items", '["b","a"]', "--as-set")
    assert result.exit_code == 0, result.stderr
    assert json.loads(put.calls.last.request.content) == ["a", "b"]
    assert put.calls.last.request.headers["If-Match"] == '"hash:1"'


def test_edit_sends_merge_patch_with_if_match(run, ditto, monkeypatch):
    ditto.get(f"/api/2/things/{A}").mock(
        return_value=httpx.Response(
            200, json={"thingId": A, "attributes": {"a": 1, "b": 2}}, headers={"ETag": '"rev:4"'}
        )
    )
    route = ditto.patch(f"/api/2/things/{A}").mock(return_value=httpx.Response(204))
    monkeypatch.setattr(click, "edit", lambda text, **_kw: text.replace('"b": 2', '"c": 3'))
    result = run("--url", URL, "things", "edit", A)
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"attributes": {"b": None, "c": 3}}
    assert route.calls.last.request.headers["If-Match"] == '"rev:4"'


def test_edit_without_changes(run, ditto, monkeypatch):
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, json={"thingId": A}))
    monkeypatch.setattr(click, "edit", lambda text, **_kw: None)
    assert "No changes" in run("--url", URL, "things", "edit", A).stderr


def test_diff(run, ditto, tmp_path):
    ditto.get(f"/api/2/things/{A}").mock(return_value=httpx.Response(200, json={"thingId": A, "attributes": {"x": 1}}))
    local = tmp_path / "a.json"
    local.write_text(json.dumps({"thingId": A, "attributes": {"x": 2}}))
    result = run("--url", URL, "things", "diff", A, "--file", str(local))
    assert result.exit_code == ExitCode.CHECK_FAILED
    assert '-    "x": 1' in result.stdout
    assert '+    "x": 2' in result.stdout
    local.write_text(json.dumps({"attributes": {"x": 1}, "thingId": A}))
    assert run("--url", URL, "things", "diff", A, "--file", str(local)).exit_code == 0


def test_messages_send_prints_responses(run, ditto):
    for thing_id, reply in ((A, {"status": "fine"}), (B, {"status": "low battery"})):
        ditto.post(f"/api/2/things/{thing_id}/inbox/messages/get-status").mock(
            return_value=httpx.Response(200, json=reply)
        )
    result = run("--url", URL, "messages", "send", "get-status", A, B, "-d", '{"verbose":true}', "--timeout", "5")
    assert result.exit_code == 0, result.stderr
    replies = {json.loads(line)["thingId"]: json.loads(line)["response"] for line in result.stdout.splitlines()}
    assert replies == {A: {"status": "fine"}, B: {"status": "low battery"}}


def test_messages_are_not_retried(run, ditto):
    route = ditto.post(f"/api/2/things/{A}/inbox/messages/reboot").mock(return_value=httpx.Response(503))
    result = run("--url", URL, "messages", "send", "reboot", A, "--timeout", "0")
    assert result.exit_code == ExitCode.PARTIAL_FAILURE
    assert route.call_count == 1

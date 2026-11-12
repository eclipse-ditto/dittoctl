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
"""DevOps, history, WoT and claim."""

import json

import httpx
import pytest
import respx

from dittoctl.core.devops import (
    duration_seconds,
    health_lines,
    purge_results,
    purge_succeeded,
    reindex_command,
    shutdown_namespace_command,
)
from dittoctl.errors import DittoctlError, ExitCode

URL = "http://ditto.test"


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


@pytest.mark.parametrize(("value", "seconds"), [("10s", 10), ("500ms", 0.5), ("2m", 120), ("1h", 3600), ("7", 7)])
def test_duration_seconds(value, seconds):
    assert duration_seconds(value) == seconds


def test_duration_seconds_rejects_garbage():
    with pytest.raises(DittoctlError):
        duration_seconds("soon")


def test_command_builders():
    assert reindex_command(["a", "b"])["headers"]["namespaces"] == ["a", "b"]
    assert "namespaces" not in reindex_command()["headers"]
    # Ditto rejects the documented shutdown command without a headers field
    assert "headers" in shutdown_namespace_command("ns")


PURGE_RESPONSE = {
    "?": {
        "?": {"type": "namespaces.responses:purgeNamespace", "status": 200, "resourceType": "thing"},
        "?1": {"type": "namespaces.responses:purgeNamespace", "status": 200, "resourceType": "policy"},
        "?2": {"type": "namespaces.responses:purgeNamespace", "status": 500, "resourceType": "thing-search"},
    }
}


def test_purge_results():
    results = purge_results(PURGE_RESPONSE)
    assert [r["resourceType"] for r in results] == ["thing", "policy", "thing-search"]
    assert [purge_succeeded(r) for r in results] == [True, True, False]
    assert purge_succeeded({"status": 200, "successful": False}) is False


def test_health_lines():
    tree = {"label": "roles", "status": "UP", "children": [{"label": "things", "status": "DOWN", "children": []}]}
    assert health_lines(tree) == [(0, "roles", "UP"), (1, "things", "DOWN")]


def test_logging_get_and_set(run, ditto):
    ditto.get("/devops/logging/things").mock(
        return_value=httpx.Response(200, json={"10.0.0.1": {"loggerConfigs": [{"logger": "ROOT", "level": "info"}]}})
    )
    result = run("--url", URL, "devops", "logging", "get", "things")
    assert result.stdout.splitlines()[1].split() == ["things", "10.0.0.1", "ROOT", "info"]
    route = ditto.put("/devops/logging").mock(return_value=httpx.Response(200, json={}))
    run("--url", URL, "devops", "logging", "set", "org.eclipse.ditto", "DEBUG")
    assert json.loads(route.calls.last.request.content) == {"logger": "org.eclipse.ditto", "level": "debug"}


def test_config_with_path(run, ditto):
    route = ditto.get("/devops/config/gateway/pod-1").mock(return_value=httpx.Response(200, json={}))
    run("--url", URL, "devops", "config", "gateway", "--instance", "pod-1", "--path", "ditto.gateway")
    assert route.calls.last.request.url.params["path"] == "ditto.gateway"


def test_piggyback_waits_longer_than_ditto(run, ditto):
    route = ditto.post("/devops/piggyback/things").mock(return_value=httpx.Response(200, json={"ok": True}))
    result = run("--url", URL, "devops", "piggyback", "things", "-d", '{"targetActorSelection":"/x"}',
                 "--timeout", "45s")  # fmt: skip
    assert result.exit_code == 0
    request = route.calls.last.request
    assert request.url.params["timeout"] == "45s"
    assert request.extensions["timeout"]["read"] == 60.0


def test_reindex(run, ditto):
    route = ditto.post("/devops/piggyback/search").mock(return_value=httpx.Response(200))
    run("--url", URL, "devops", "reindex", "-n", "ns1")
    assert json.loads(route.calls.last.request.content)["headers"]["namespaces"] == ["ns1"]
    run("--url", URL, "devops", "reindex", "--thing", "ns1:a")
    body = json.loads(route.calls.last.request.content)
    assert body["piggybackCommand"] == {"type": "thing-search.sudo.commands:sudoUpdateThing", "thingId": "ns1:a"}


def piggyback_router(purge: httpx.Response):
    def handler(request: httpx.Request) -> httpx.Response:
        command_type = json.loads(request.content)["piggybackCommand"]["type"]
        if command_type == "common.commands:shutdown":
            return httpx.Response(408, json={"status": 408, "error": "command.timeout"})
        if command_type == "namespaces.commands:purgeNamespace":
            return purge
        return httpx.Response(200, json={"status": 200})

    return handler


def test_namespace_erase(run, ditto):
    route = ditto.post("/devops/piggyback").mock(side_effect=piggyback_router(httpx.Response(200, json=PURGE_RESPONSE)))
    result = run("--url", URL, "devops", "namespace", "erase", "ns1", "--confirm-namespace", "ns1")
    commands = [json.loads(c.request.content)["piggybackCommand"]["type"] for c in route.calls]
    assert commands == [
        "namespaces.commands:blockNamespace",
        "common.commands:shutdown",
        "namespaces.commands:purgeNamespace",
        "namespaces.commands:unblockNamespace",
    ]
    # thing-search reported 500 in PURGE_RESPONSE
    assert result.exit_code == ExitCode.ERROR
    assert "thing-search: FAILED" in result.stderr


def test_namespace_erase_unconfirmed_purge_still_unblocks(run, ditto):
    timeout = httpx.Response(408, json={"status": 408, "error": "command.timeout", "message": "timeout"})
    route = ditto.post("/devops/piggyback").mock(side_effect=piggyback_router(timeout))
    result = run("--url", URL, "devops", "namespace", "erase", "ns1", "--confirm-namespace", "ns1")
    assert result.exit_code == ExitCode.ERROR
    assert "didn't confirm the erasure" in result.stderr
    assert json.loads(route.calls.last.request.content)["piggybackCommand"]["type"] == (
        "namespaces.commands:unblockNamespace"
    )


def test_namespace_erase_needs_confirmation(run, ditto):
    route = ditto.post("/devops/piggyback").mock(return_value=httpx.Response(200))
    result = run("--url", URL, "devops", "namespace", "erase", "ns1")
    assert result.exit_code == ExitCode.ABORTED
    assert route.call_count == 0


def test_status(run, ditto):
    ditto.get("/status").mock(
        return_value=httpx.Response(200, json={"service-version": "3.9.8", "roles": {"things": {}, "gateway": {}}})
    )
    ditto.get("/status/health").mock(
        return_value=httpx.Response(200, json={"label": "roles", "status": "UP",
                                               "children": [{"label": "things", "status": "DOWN"}]})
    )  # fmt: skip
    lines = run("--url", URL, "devops", "status", "--health").stdout.splitlines()
    assert lines[0].split() == ["service-version:", "3.9.8"]
    assert lines[1].endswith("gateway, things")
    assert "  things: DOWN  <--" in lines


def test_history(run, ditto):
    stream = b'data: {"_revision":1}\n\ndata: {"_revision":2}\n\n'
    route = ditto.get("/api/2/things/ns:a").mock(return_value=httpx.Response(200, content=stream))
    result = run("--url", URL, "things", "history", "ns:a", "--from-revision", "-5", "--to-revision", "0",
                 "--fields", "_revision")  # fmt: skip
    assert [json.loads(line)["_revision"] for line in result.stdout.splitlines()] == [1, 2]
    request = route.calls.last.request
    assert request.headers["Accept"] == "text/event-stream"
    assert dict(request.url.params) == {
        "from-historical-revision": "-5", "to-historical-revision": "0", "fields": "_revision",
    }  # fmt: skip
    assert run("--url", URL, "things", "history", "ns:a").exit_code == ExitCode.ERROR


def test_td_and_wot_directory(run, ditto):
    td = ditto.get("/api/2/things/ns:a/features/lamp").mock(return_value=httpx.Response(200, json={"title": "Lamp"}))
    assert json.loads(run("--url", URL, "things", "td", "ns:a", "--feature", "lamp").stdout) == {"title": "Lamp"}
    assert td.calls.last.request.headers["Accept"] == "application/td+json"
    ditto.get("/.well-known/wot").mock(return_value=httpx.Response(200, json={"@type": "ThingDirectory"}))
    assert json.loads(run("--url", URL, "wot", "directory").stdout) == {"@type": "ThingDirectory"}


def test_migrate_definition(run, ditto):
    route = ditto.post("/api/2/things/ns:a/migrateDefinition").mock(
        return_value=httpx.Response(200, json={"mergeStatus": "DRY_RUN"})
    )
    result = run("--url", URL, "things", "migrate-definition", "ns:a", "--definition", "https://m/lamp-2.tm.jsonld",
                 "--payload", '{"attributes":{"x":1}}', "--patch-condition", "features/lamp=not(exists(features/lamp))",
                 "--init-defaults", "--dry-run")  # fmt: skip
    assert result.exit_code == 0, result.stderr
    request = route.calls.last.request
    assert request.url.params["dry-run"] == "true"
    assert json.loads(request.content) == {
        "thingDefinitionUrl": "https://m/lamp-2.tm.jsonld",
        "migrationPayload": {"attributes": {"x": 1}},
        "patchConditions": {"thing:/features/lamp": "not(exists(features/lamp))"},
        "initializeMissingPropertiesFromDefaults": True,
    }
    assert json.loads(result.stdout) == {"mergeStatus": "DRY_RUN"}


def test_claim(run, ditto):
    route = ditto.post("/api/2/things/ns:a/inbox/claim").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert json.loads(run("--url", URL, "messages", "claim", "ns:a", "--timeout", "3").stdout) == {"ok": True}
    assert route.calls.last.request.url.params["timeout"] == "3"


def test_bulk_failure_reasons_are_shown(run, ditto):
    ditto.patch("/api/2/things/ns:a").mock(
        return_value=httpx.Response(400, json={"status": 400, "error": "wot:payload.validation.error",
                                               "message": "The provided payload did not conform"})
    )  # fmt: skip
    result = run("--url", URL, "things", "set", "attributes/x", "1", "ns:a")
    assert result.exit_code == ExitCode.PARTIAL_FAILURE
    assert "ns:a: 400 wot:payload.validation.error: The provided payload did not conform" in result.stderr

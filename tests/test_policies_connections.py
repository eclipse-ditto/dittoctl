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

import httpx
import pytest
import respx

from dittoctl.core.bulk import Category
from dittoctl.core.client import DittoClient
from dittoctl.core.connections import connection_path, redact_secrets, redact_uri, send_command
from dittoctl.core.policies import migrate_subjects, policy_path, subject_migration_operation
from dittoctl.core.writes import message_operation
from dittoctl.errors import DittoctlError, ExitCode

BASE = "http://ditto.test"
U1 = "11111111-1111-4111-8111-111111111111"
POLICY = {
    "policyId": "ns:p",
    "entries": {
        "owner": {"subjects": {"nginx:ditto": {"type": "basic"}}, "resources": {}},
        "users": {
            "subjects": {
                f"oldidp:{U1}": {"type": "user", "expiry": "2030-01-01T00:00:00Z"},
                "oldidp:role-admins": {"type": "group"},
            },
            "resources": {"thing:/": {"grant": ["READ"], "revoke": []}},
        },
    },
}
PATTERN = re.compile(r"oldidp:(?P<sub>[0-9a-f-]{36})")
TEMPLATE = r"newidp:fed-sub:\g<sub>"


@pytest.fixture
def client():
    with DittoClient(BASE, sleep=lambda _s: None) as c:
        yield c


def test_policy_path_encodes_segments():
    assert policy_path("ns:p") == "/api/2/policies/ns:p"
    assert policy_path("ns:p", "entries", "my label", "subjects", "a:b/c") == (
        "/api/2/policies/ns:p/entries/my%20label/subjects/a:b%2Fc"
    )


def test_migrate_subjects_adds_twins_with_same_value():
    migrated, changes = migrate_subjects(POLICY, PATTERN, TEMPLATE)
    subjects = migrated["entries"]["users"]["subjects"]
    assert subjects[f"newidp:fed-sub:{U1}"] == {"type": "user", "expiry": "2030-01-01T00:00:00Z"}
    assert f"oldidp:{U1}" in subjects
    assert "newidp:fed-sub:role-admins" not in subjects  # doesn't match the pattern
    assert [c.describe() for c in changes] == [f"users: add oldidp:{U1} -> newidp:fed-sub:{U1}"]
    assert POLICY["entries"]["users"]["subjects"].keys() == {f"oldidp:{U1}", "oldidp:role-admins"}  # not mutated


def test_migrate_subjects_is_idempotent_and_can_replace():
    migrated, _ = migrate_subjects(POLICY, PATTERN, TEMPLATE)
    assert migrate_subjects(migrated, PATTERN, TEMPLATE)[1] == []
    replaced, changes = migrate_subjects(POLICY, PATTERN, TEMPLATE, remove_old=True)
    assert f"oldidp:{U1}" not in replaced["entries"]["users"]["subjects"]
    assert changes[0].removed_old
    assert migrate_subjects(POLICY, PATTERN, TEMPLATE, labels={"owner"})[1] == []


@respx.mock
def test_subject_migration_operation_writes_with_if_match_and_retries(client):
    respx.get(f"{BASE}/api/2/policies/ns:p").mock(
        return_value=httpx.Response(200, json=POLICY, headers={"ETag": '"rev:3"'})
    )
    put = respx.put(f"{BASE}/api/2/policies/ns:p").mock(
        side_effect=[
            httpx.Response(412, json={"status": 412, "error": "policies:precondition.failed", "message": "x"}),
            httpx.Response(204),
        ]
    )
    operation = subject_migration_operation(client, PATTERN, TEMPLATE, allow_lockout=True)
    outcome = operation("ns:p")
    assert outcome.category == Category.OK
    assert put.call_count == 2
    request = put.calls.last.request
    assert request.headers["If-Match"] == '"rev:3"'
    assert request.url.params["allow-policy-lockout"] == "true"
    assert f"newidp:fed-sub:{U1}" in json.loads(request.content)["entries"]["users"]["subjects"]


@respx.mock
def test_subject_migration_dry_run_and_unchanged(client):
    respx.get(f"{BASE}/api/2/policies/ns:p").mock(return_value=httpx.Response(200, json=POLICY))
    planned = subject_migration_operation(client, PATTERN, TEMPLATE, dry_run=True)("ns:p")
    assert planned.category == Category.PLANNED
    assert planned.detail["changes"] == [f"users: add oldidp:{U1} -> newidp:fed-sub:{U1}"]
    nothing = subject_migration_operation(client, re.compile("nomatch:.*"), "x")("ns:p")
    assert nothing.category == Category.UNCHANGED


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("amqps://user:s3cret@broker:5671/vhost", "amqps://user:***@broker:5671/vhost"),
        ("tcp://broker:1883", "tcp://broker:1883"),
        ("http://user@host", "http://user@host"),
    ],
)
def test_redact_uri(uri, expected):
    assert redact_uri(uri) == expected


def test_redact_secrets_in_log_messages():
    message = (
        "Message headers: [if-none-match=*, authorization=Basic ZGl0dG86ZGl0dG8=, x-real-ip=1.2.3.4] "
        '{"headers":{"Authorization":"Bearer eyJhbGciOi.payload.sig"}} uri=mqtt://u:pw@broker:1883'
    )
    redacted = redact_secrets(message)
    assert "ZGl0dG86ZGl0dG8" not in redacted
    assert "eyJhbGciOi" not in redacted
    assert ":pw@" not in redacted
    assert "authorization=Basic ***" in redacted
    assert '"Authorization":"Bearer ***"' in redacted
    assert "mqtt://u:***@broker:1883" in redacted


@respx.mock
def test_send_command(client):
    route = respx.post(f"{BASE}/api/2/connections/my%2Fconn/command").mock(return_value=httpx.Response(200))
    assert connection_path("my/conn") == "/api/2/connections/my%2Fconn"
    send_command(client, "my/conn", "open")
    assert route.calls.last.request.content == b"connectivity.commands:openConnection"
    assert route.calls.last.request.headers["Content-Type"] == "text/plain"


@respx.mock
def test_message_pagination(client):
    route = respx.post(f"{BASE}/api/2/things/ns:a/inbox/messages/history").mock(
        side_effect=[
            httpx.Response(200, json={"values": [1, 2], "next": "t1"}),
            httpx.Response(200, json={"values": [3], "next": "t2"}),
            httpx.Response(200, json={"values": [4]}),
        ]
    )
    operation = message_operation(client, "history", {"from": "2026-11-01"}, timeout=5, paginate=("next", "token"))
    outcome = operation("ns:a")
    assert outcome.category == Category.OK
    assert [page["values"] for page in outcome.detail] == [[1, 2], [3], [4]]
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert bodies == [
        {"from": "2026-11-01"},
        {"from": "2026-11-01", "token": "t1"},
        {"from": "2026-11-01", "token": "t2"},
    ]


@respx.mock
def test_message_pagination_stops_at_max_pages(client):
    respx.post(f"{BASE}/api/2/things/ns:a/inbox/messages/history").mock(
        return_value=httpx.Response(200, json={"next": "again"})
    )
    outcome = message_operation(client, "history", None, timeout=5, paginate=("next", "next"), max_pages=3)("ns:a")
    assert outcome.category == Category.FAILED
    assert len(outcome.detail) == 3


def test_message_pagination_needs_object_payload(client):
    with pytest.raises(DittoctlError, match="JSON object"):
        message_operation(client, "x", [1, 2], paginate=("next", "next"))


# --- CLI ---------------------------------------------------------------------------------------

URL = "http://ditto.test"


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


def test_cli_subjects_add_and_remove(run, ditto):
    put = ditto.put("/api/2/policies/ns:p/entries/users/subjects/nginx:bob").mock(return_value=httpx.Response(201))
    delete = ditto.delete("/api/2/policies/ns:p/entries/users/subjects/nginx:bob").mock(
        return_value=httpx.Response(204)
    )
    run("--url", URL, "policies", "subjects", "add", "ns:p", "users", "nginx:bob", "--expiring-at", "2031-01-01T00:00Z")
    assert json.loads(put.calls.last.request.content) == {"type": "added by dittoctl", "expiry": "2031-01-01T00:00Z"}
    run("--url", URL, "policies", "subjects", "remove", "ns:p", "users", "nginx:bob", "--allow-lockout")
    assert delete.calls.last.request.url.params["allow-policy-lockout"] == "true"


def test_cli_policies_list_and_migrate_by_filter(run, ditto):
    ditto.get("/api/2/search/things").mock(
        return_value=httpx.Response(200, json={"items": [{"policyId": "ns:p"}, {"policyId": "ns:p"}, {"thingId": "x"}]})
    )
    assert run("--url", URL, "policies", "list", "-f", "exists(attributes/x)").stdout == "ns:p\n"
    ditto.get("/api/2/policies/ns:p").mock(return_value=httpx.Response(200, json=POLICY, headers={"ETag": '"rev:1"'}))
    put = ditto.put("/api/2/policies/ns:p").mock(return_value=httpx.Response(204))
    result = run("--url", URL, "policies", "subjects", "migrate", "-f", "exists(attributes/x)",
                 "--match", PATTERN.pattern, "--template", TEMPLATE)  # fmt: skip
    assert result.exit_code == 0, result.stderr
    assert "Migrate subjects: 1 of 1 policies" in result.stderr
    assert put.call_count == 1


def test_cli_migrate_rejects_bad_regex(run):
    result = run("--url", URL, "policies", "subjects", "migrate", "ns:p", "--match", "(", "--template", "x")
    assert result.exit_code == ExitCode.ERROR
    assert "--match" in result.stderr


def test_cli_check_permissions(run, ditto):
    route = ditto.post("/api/2/checkPermissions").mock(
        return_value=httpx.Response(200, json={"thing:/attributes": True, "policy:/": False})
    )
    result = run("--url", URL, "policies", "check", "ns:t", "--resource", "thing:/attributes", "--resource", "policy:/",
                 "--permission", "WRITE")  # fmt: skip
    assert result.exit_code == ExitCode.CHECK_FAILED
    assert result.stdout.splitlines() == ["allowed  thing:/attributes (WRITE)", "denied   policy:/ (WRITE)"]
    assert json.loads(route.calls.last.request.content)["policy:/"] == {
        "resource": "policy:/", "entityId": "ns:t", "hasPermissions": ["WRITE"],
    }  # fmt: skip


def test_cli_policy_get_resolved(run, ditto):
    route = ditto.get("/api/2/policies/ns:p/entries/users").mock(return_value=httpx.Response(200, json={}))
    run("--url", URL, "policies", "get", "ns:p", "--path", "entries/users", "--resolved")
    assert route.calls.last.request.url.params["policy-view"] == "resolved"


def test_cli_token_integration(run, ditto):
    route = ditto.post("/api/2/policies/ns:p/entries/users/actions/activateTokenIntegration").mock(
        return_value=httpx.Response(204)
    )
    assert run("--url", URL, "policies", "activate-token-integration", "ns:p", "--label", "users").exit_code == 0
    assert route.call_count == 1


def test_cli_connections_list_redacts_passwords(run, ditto):
    ditto.get("/api/2/connections").mock(
        return_value=httpx.Response(200, json=[{"id": "c1", "name": "n", "connectionType": "amqp-091",
                                                "connectionStatus": "open", "uri": "amqp://u:secret@b:5672"}])
    )  # fmt: skip
    result = run("--url", URL, "connections", "list")
    assert "amqp://u:***@b:5672" in result.stdout
    assert "secret" not in result.stdout
    assert run("--url", URL, "connections", "list", "-o", "ids").stdout == "c1\n"


def test_cli_connection_test_and_commands(run, ditto):
    test = ditto.post("/api/2/connections").mock(return_value=httpx.Response(200))
    result = run("--url", URL, "connections", "test", "-d", '{"connectionType":"mqtt"}')
    assert "Connection test succeeded" in result.stderr
    assert test.calls.last.request.url.params["dry-run"] == "true"
    command = ditto.post("/api/2/connections/c1/command").mock(return_value=httpx.Response(200))
    for name, expected in (("open", "openConnection"), ("close", "closeConnection"),
                           ("reset-metrics", "resetConnectionMetrics")):  # fmt: skip
        assert run("--url", URL, "connections", name, "c1").exit_code == 0
        assert command.calls.last.request.content.decode() == f"connectivity.commands:{expected}"


def test_cli_connection_logs_redacted(run, ditto):
    entry = {"timestamp": "2026-11-06T10:00:00Z", "level": "success", "category": "target", "type": "dispatched",
             "message": "headers: [authorization=Basic c2VjcmV0]"}  # fmt: skip
    ditto.get("/api/2/connections/c1/logs").mock(
        return_value=httpx.Response(200, json={"connectionId": "c1", "enabledSince": "2026-11-06T09:00:00Z",
                                               "connectionLogs": [entry]})
    )  # fmt: skip
    result = run("--url", URL, "connections", "logs", "c1", "-o", "ndjson")
    assert json.loads(result.stdout)["message"] == "headers: [authorization=Basic ***]"
    assert "not enabled" not in result.stderr
    raw = run("--url", URL, "connections", "logs", "c1", "-o", "ndjson", "--no-redact")
    assert "c2VjcmV0" in raw.stdout


def test_cli_things_get_live(run, ditto):
    route = ditto.get("/api/2/things/ns:a").mock(return_value=httpx.Response(200, json={}))
    run("--url", URL, "things", "get", "ns:a", "--live", "--live-timeout", "3", "--live-timeout-strategy", "use-twin")
    request = route.calls.last.request
    assert request.url.params["channel"] == "live"
    assert request.url.params["timeout"] == "3s"
    assert request.headers["live-channel-timeout-strategy"] == "use-twin"


def test_cli_messages_paginate(run, ditto):
    ditto.post("/api/2/things/ns:a/inbox/messages/history").mock(
        side_effect=[httpx.Response(200, json={"v": 1, "next": "t"}), httpx.Response(200, json={"v": 2})]
    )
    result = run("--url", URL, "messages", "send", "history", "ns:a", "-d", "{}", "--paginate", "next:token")
    assert result.exit_code == 0, result.stderr
    pages = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(p["page"], p["response"]["v"]) for p in pages] == [(1, 1), (2, 2)]
    refused = run("--url", URL, "messages", "send", "history", "ns:a", "--paginate", "next", "--timeout", "0")
    assert refused.exit_code == ExitCode.ERROR

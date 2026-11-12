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
import base64
import json

import httpx
import respx

from dittoctl import __version__
from dittoctl.config import Config
from dittoctl.errors import ExitCode

URL = "http://ditto.test"
THING = "/api/2/things/org.example:sensor-1"


def add_basic_context(run, name="local"):
    result = run("config", "add-context", name, "--url", URL, "--auth", "basic", "--username", "ditto")
    assert result.exit_code == 0, result.stderr
    result = run("auth", "login", "--password-stdin", stdin="ditto-pw\n")
    assert result.exit_code == 0, result.stderr


def test_version(run):
    result = run("--version")
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_usage_error_exits_with_1(run):
    result = run("api")
    assert result.exit_code == ExitCode.ERROR
    assert "Missing argument" in result.stderr


def test_without_context_or_url(run):
    result = run("whoami")
    assert result.exit_code == ExitCode.ERROR
    assert "no context selected" in result.stderr


def test_context_lifecycle(run):
    add_basic_context(run, "local")
    result = run("config", "add-context", "prod", "--url", "https://ditto.example.com/", "--protected")
    assert result.exit_code == 0, result.stderr

    listed = run("config", "get-contexts").stdout
    assert "local" in listed
    assert "https://ditto.example.com" in listed
    assert run("config", "current-context").stdout.strip() == "local"

    assert run("config", "use-context", "prod").exit_code == 0
    assert run("config", "current-context").stdout.strip() == "prod"
    assert 'url = "https://ditto.example.com"' in run("config", "view", "prod").stdout

    duplicate = run("config", "add-context", "prod", "--url", URL)
    assert duplicate.exit_code == ExitCode.ERROR
    assert "--overwrite" in duplicate.stderr

    assert run("config", "delete-context", "local").exit_code == 0
    config = Config.load()
    assert set(config.contexts) == {"prod"}
    assert config.contexts["prod"].protected


def test_add_context_validates(run):
    result = run("config", "add-context", "x", "--url", URL, "--auth", "oidc", "--issuer", "https://idp")
    assert result.exit_code == ExitCode.ERROR
    assert "client id" in result.stderr


@respx.mock
def test_whoami_with_basic_auth(run):
    add_basic_context(run)
    route = respx.get(f"{URL}/api/2/whoami").mock(
        return_value=httpx.Response(
            200, json={"defaultSubject": "nginx:ditto", "subjects": ["nginx:ditto", "nginx:admins"]}
        )
    )
    result = run("whoami")
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == ["nginx:ditto (default)", "nginx:admins"]
    expected = "Basic " + base64.b64encode(b"ditto:ditto-pw").decode()
    assert route.calls.last.request.headers["Authorization"] == expected


@respx.mock
def test_auth_status_and_logout(run):
    add_basic_context(run)
    assert "authenticated: yes" in run("auth", "status").stdout
    assert run("auth", "logout").exit_code == 0
    assert "authenticated: no" in run("auth", "status").stdout
    result = run("whoami")
    assert result.exit_code == ExitCode.AUTH
    assert "no password" in result.stderr


@respx.mock
def test_api_with_url_token_and_conditions(run, monkeypatch):
    monkeypatch.setenv("DITTOCTL_TOKEN", "tkn")
    route = respx.patch(f"{URL}{THING}/attributes").mock(return_value=httpx.Response(204))
    result = run(
        "--url", URL,
        "api", "patch", f"{THING}/attributes",
        "-d", '{"room":"lab"}',
        "--if-match", "rev:4",
        "--if-equal", "skip",
        "--condition", "exists(attributes)",
        "--patch-condition", "/attributes/room=ne(attributes/room,\"lab\")",
    )  # fmt: skip
    assert result.exit_code == 0, result.stderr
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer tkn"
    assert request.headers["Content-Type"] == "application/merge-patch+json"
    assert request.headers["If-Match"] == '"rev:4"'
    assert request.headers["If-Equal"] == "skip"
    assert json.loads(request.headers["merge-thing-patch-conditions"]) == {
        "/attributes/room": 'ne(attributes/room,"lab")'
    }
    assert request.url.params["condition"] == "exists(attributes)"


@respx.mock
def test_api_reads_body_from_stdin_and_prints_json(run, monkeypatch):
    monkeypatch.setenv("DITTOCTL_TOKEN", "tkn")
    thing = {"thingId": "org.example:sensor-1", "policyId": "org.example:sensor-1"}
    route = respx.put(f"{URL}{THING}").mock(return_value=httpx.Response(201, json=thing))
    result = run("--url", URL, "api", "PUT", THING, "-d", "@-", "--if-none-match", "*", stdin=json.dumps(thing))
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == thing
    assert route.calls.last.request.headers["If-None-Match"] == "*"
    assert route.calls.last.request.headers["Content-Type"] == "application/json"


@respx.mock
def test_api_query_params_and_ndjson(run):
    route = respx.get(f"{URL}/api/2/search/things").mock(
        return_value=httpx.Response(200, json=[{"thingId": "a"}, {"thingId": "b"}])
    )
    result = run("--url", URL, "api", "GET", "/api/2/search/things", "-q", "filter=exists(thingId)", "-o", "ndjson")
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == ['{"thingId":"a"}', '{"thingId":"b"}']
    assert route.calls.last.request.url.params["filter"] == "exists(thingId)"


@respx.mock
def test_api_not_found_exit_code_and_message(run):
    respx.get(f"{URL}{THING}").mock(
        return_value=httpx.Response(
            404,
            json={"status": 404, "error": "things:thing.notfound", "message": "not found", "description": "Check ID"},
        )
    )
    result = run("--url", URL, "api", "GET", THING)
    assert result.exit_code == ExitCode.NOT_FOUND
    assert "things:thing.notfound" in result.stderr
    assert "Check ID" in result.stderr


@respx.mock
def test_verbose_prints_redacted_curl(run, monkeypatch):
    monkeypatch.setenv("DITTOCTL_TOKEN", "very-secret")
    respx.get(f"{URL}/api/2/whoami").mock(return_value=httpx.Response(200, json={"subjects": []}))
    result = run("-v", "--url", URL, "--correlation-id", "trace", "-H", "x-extra: 1", "whoami")
    assert result.exit_code == 0, result.stderr
    assert "curl -X GET" in result.stderr
    assert "very-secret" not in result.stderr
    assert "Bearer ***" in result.stderr
    assert "correlation-id: trace-1" in result.stderr
    assert "x-extra: 1" in result.stderr


def test_completion_script(run):
    result = run("completion", "zsh")
    assert result.exit_code == 0
    assert "_DITTOCTL_COMPLETE" in result.stdout

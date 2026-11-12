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

from dittoctl.auth.base import AuthProvider
from dittoctl.config import Context
from dittoctl.core.client import DittoClient
from dittoctl.core.conditions import Conditions, IfEqual
from dittoctl.core.curl import to_curl
from dittoctl.errors import DittoctlError, DittoError, ExitCode

BASE = "http://ditto.test"
THING = "/api/2/things/org.example:sensor-1"


class RefreshingAuth(AuthProvider):
    """Hands out token-1 until refresh() is called, then token-2."""

    def __init__(self) -> None:
        super().__init__(Context(name="test", url=BASE), store=None)  # type: ignore[arg-type]
        self.token = "token-1"
        self.refreshes = 0

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def refresh(self) -> bool:
        self.refreshes += 1
        self.token = "token-2"
        return True


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(sleeps):
    with DittoClient(BASE, correlation_id="run", sleep=sleeps.append) as c:
        yield c


@respx.mock
def test_get_parses_json_and_sets_correlation_id_and_user_agent(client):
    route = respx.get(f"{BASE}/api/2/whoami").mock(
        return_value=httpx.Response(200, json={"subjects": ["nginx:ditto"]}, headers={"ETag": '"rev:1"'})
    )
    first = client.get("/api/2/whoami")
    client.get("/api/2/whoami")
    assert first.body == {"subjects": ["nginx:ditto"]}
    assert first.etag == '"rev:1"'
    requests = [call.request for call in route.calls]
    assert [r.headers["correlation-id"] for r in requests] == ["run-1", "run-2"]
    assert requests[0].headers["user-agent"].startswith("dittoctl/")


@respx.mock
def test_explicit_correlation_id_header_wins(client):
    route = respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(200, json={}))
    client.get(THING, headers={"correlation-id": "mine"})
    assert route.calls.last.request.headers["correlation-id"] == "mine"


@respx.mock
def test_conditions_become_headers_and_url_encoded_params(client):
    route = respx.patch(f"{BASE}{THING}/attributes").mock(return_value=httpx.Response(204))
    conditions = Conditions(if_match="rev:7", if_equal=IfEqual.SKIP, condition='eq(attributes/room,"Küche")')
    response = client.patch(f"{THING}/attributes", json={"room": "lab"}, conditions=conditions)
    request = route.calls.last.request
    assert response.status == 204
    assert request.headers["If-Match"] == '"rev:7"'
    assert request.headers["If-Equal"] == "skip"
    assert request.headers["Content-Type"] == "application/merge-patch+json"
    assert request.url.params["condition"] == 'eq(attributes/room,"Küche")'
    assert json.loads(request.content) == {"room": "lab"}


@respx.mock
def test_put_json_uses_application_json(client):
    route = respx.put(f"{BASE}{THING}").mock(return_value=httpx.Response(201, json={"thingId": "org.example:sensor-1"}))
    client.put(THING, json={})
    assert route.calls.last.request.headers["Content-Type"] == "application/json"


@respx.mock
def test_ditto_error_body_is_mapped(client):
    respx.get(f"{BASE}{THING}").mock(
        return_value=httpx.Response(
            404,
            json={
                "status": 404,
                "error": "things:thing.notfound",
                "message": "The Thing with ID 'org.example:sensor-1' could not be found.",
                "description": "Check if the ID of your requested Thing was correct.",
            },
            headers={"correlation-id": "run-1"},
        )
    )
    with pytest.raises(DittoError) as info:
        client.get(THING)
    error = info.value
    assert error.status == 404
    assert error.error == "things:thing.notfound"
    assert error.description.startswith("Check if")
    assert error.correlation_id == "run-1"
    assert error.exit_code == ExitCode.NOT_FOUND
    assert str(error).startswith("404 things:thing.notfound: The Thing")


@respx.mock
def test_html_error_page_is_reduced_to_reason_phrase(client):
    page = "<html>\n<head><title>401 Authorization Required</title></head>\n<body>nginx</body>\n</html>"
    respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(401, text=page, headers={"Content-Type": "text/html"}))
    with pytest.raises(DittoError) as info:
        client.get(THING)
    assert str(info.value) == "401: Unauthorized"
    assert info.value.body == page


@respx.mock
def test_plain_text_error_body_is_kept(client):
    respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(502, text="upstream unavailable"))
    with pytest.raises(DittoError, match="502: upstream unavailable"):
        client.get(THING, retry=False)


@respx.mock
def test_raise_for_status_false_returns_error_response(client):
    respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(412, json={"status": 412}))
    assert client.get(THING, raise_for_status=False).status == 412


@respx.mock
def test_retries_idempotent_requests_honouring_retry_after(client, sleeps):
    route = respx.get(f"{BASE}{THING}").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "2"}),
            httpx.Response(429),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert client.get(THING).body == {"ok": True}
    assert route.call_count == 3
    assert sleeps == [2.0, 1.0]  # Retry-After, then backoff 0.5 * 2**1


@respx.mock
def test_gives_up_after_max_retries(client, sleeps):
    route = respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(503))
    with pytest.raises(DittoError):
        client.get(THING)
    assert route.call_count == 4
    assert len(sleeps) == 3


@respx.mock
def test_post_is_not_retried_by_default(client):
    route = respx.post(f"{BASE}{THING}/inbox/messages/reboot").mock(return_value=httpx.Response(503))
    with pytest.raises(DittoError):
        client.post(f"{THING}/inbox/messages/reboot", json={})
    assert route.call_count == 1


@respx.mock
def test_transport_errors_are_retried_then_reported(client):
    route = respx.get(f"{BASE}{THING}").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(DittoctlError, match="refused"):
        client.get(THING)
    assert route.call_count == 4


@respx.mock
def test_401_triggers_one_refresh_and_retry(sleeps):
    auth = RefreshingAuth()
    route = respx.get(f"{BASE}{THING}").mock(side_effect=[httpx.Response(401), httpx.Response(200, json={})])
    with DittoClient(BASE, auth, sleep=sleeps.append) as client:
        client.get(THING)
    assert auth.refreshes == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == ["Bearer token-1", "Bearer token-2"]


@respx.mock
def test_persistent_401_is_not_refreshed_twice():
    auth = RefreshingAuth()
    respx.get(f"{BASE}{THING}").mock(return_value=httpx.Response(401))
    with DittoClient(BASE, auth) as client, pytest.raises(DittoError) as info:
        client.get(THING)
    assert auth.refreshes == 1
    assert info.value.exit_code == ExitCode.AUTH


def test_relative_path_is_rejected(client):
    with pytest.raises(DittoctlError, match="must start with"):
        client.get("api/2/things")


def test_curl_rendering_redacts_credentials():
    request = httpx.Request(
        "PATCH",
        f"{BASE}{THING}",
        headers={"Authorization": "Bearer secret-token", "If-Match": '"rev:1"', "x-ditto-pre-authenticated": "a:b"},
        content=b'{"a":1}',
    )
    curl = to_curl(request)
    assert "secret-token" not in curl
    assert "'Authorization: Bearer ***'" in curl
    assert "'x-ditto-pre-authenticated: ***'" in curl
    assert "'If-Match: \"rev:1\"'" in curl
    assert "--data-raw '{\"a\":1}'" in curl


def test_errors_not_from_ditto_name_the_request():
    response = httpx.Response(
        404,
        text="<html><body>404 Not Found</body></html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "http://ditto.test/status"),
    )
    error = DittoError.from_response(response)
    assert error.message == "Not Found"
    assert error.description.startswith("GET /status was answered without a Ditto error")
    assert "may not be exposed" in error.description

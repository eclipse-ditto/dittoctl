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
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import pytest
import respx

from dittoctl.auth.oidc import OidcAuth, TokenSet, code_challenge, generate_code_verifier
from dittoctl.auth.store import FileStore
from dittoctl.config import AuthConfig, Context
from dittoctl.errors import AuthError

ISSUER = "https://idp.test/realms/iot"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"
DEVICE_URL = f"{ISSUER}/protocol/openid-connect/auth/device"
AUTH_URL = f"{ISSUER}/protocol/openid-connect/auth"


def make_jwt(claims: dict) -> str:
    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'none'})}.{b64(claims)}.sig"


@pytest.fixture
def store(tmp_path):
    return FileStore(tmp_path / "secrets.json")


@pytest.fixture
def discovery():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{ISSUER}/.well-known/openid-configuration").mock(
            return_value=httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": AUTH_URL,
                    "token_endpoint": TOKEN_URL,
                    "device_authorization_endpoint": DEVICE_URL,
                },
            )
        )
        yield mock


def make_auth(store, flow="pkce", messages=None, **kwargs) -> OidcAuth:
    context = Context(
        name="prod",
        url="https://ditto.test",
        auth=AuthConfig(
            method="oidc",
            issuer=ISSUER,
            client_id="dittoctl",
            flow=flow,
            scopes=["openid", "offline_access"],
            extra_params={"audience": "ditto"},
        ),
    )
    notify = messages.append if messages is not None else (lambda _m: None)
    return OidcAuth(context, store, notify=notify, sleep=lambda _s: None, **kwargs)


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_code_challenge_matches_rfc7636_appendix_b():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_verifier_is_within_rfc_length():
    assert 43 <= len(generate_code_verifier()) <= 128


def test_client_credentials_login_and_headers(store, discovery):
    route = discovery.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-1", "expires_in": 300})
    )
    auth = make_auth(store, flow="client-credentials")
    auth.login(secret="s3cret")
    assert auth.headers() == {"Authorization": "Bearer at-1"}
    sent = form(route.calls.last.request)
    assert sent == {
        "grant_type": "client_credentials",
        "scope": "openid offline_access",
        "audience": "ditto",
        "client_id": "dittoctl",
        "client_secret": "s3cret",
    }
    assert store.get("prod/client-secret") == "s3cret"


def test_client_credentials_requires_secret(store, discovery):
    with pytest.raises(AuthError, match="client secret"):
        make_auth(store, flow="client-credentials").login()


def test_client_credentials_fetches_new_token_when_expired(store, discovery):
    discovery.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "at-2", "expires_in": 300}))
    auth = make_auth(store, flow="client-credentials")
    store.set("prod/client-secret", "s3cret")
    store.set(
        "prod/oidc-tokens",
        TokenSet(access_token="old", issuer=ISSUER, client_id="dittoctl", expires_at=time.time() - 10).to_json(),
    )
    assert auth.bearer_token() == "at-2"


def test_expired_token_is_refreshed(store, discovery):
    route = discovery.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-new", "expires_in": 300})
    )
    store.set(
        "prod/oidc-tokens",
        TokenSet(
            access_token="at-old",
            issuer=ISSUER,
            client_id="dittoctl",
            refresh_token="rt-1",
            id_token="id-1",
            expires_at=time.time() - 1,
        ).to_json(),
    )
    auth = make_auth(store)
    assert auth.bearer_token() == "at-new"
    assert form(route.calls.last.request)["refresh_token"] == "rt-1"
    saved = TokenSet.from_json(store.get("prod/oidc-tokens"))
    # the provider didn't rotate the refresh token or return a new id token: the old ones are kept
    assert saved.refresh_token == "rt-1"
    assert saved.id_token == "id-1"


def test_valid_token_is_used_without_network(store):
    store.set(
        "prod/oidc-tokens",
        TokenSet(access_token="at", issuer=ISSUER, client_id="dittoctl", expires_at=time.time() + 600).to_json(),
    )
    with respx.mock(assert_all_mocked=True):
        assert make_auth(store).bearer_token() == "at"


def test_tokens_of_another_client_are_ignored(store):
    store.set("prod/oidc-tokens", TokenSet(access_token="at", issuer=ISSUER, client_id="other").to_json())
    with pytest.raises(AuthError, match="not logged in"):
        make_auth(store).bearer_token()


def test_token_expiry_falls_back_to_jwt_exp(store, discovery):
    access_token = make_jwt({"sub": "alice", "exp": 2_000_000_000})
    discovery.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": access_token}))
    store.set("prod/client-secret", "s")
    auth = make_auth(store, flow="client-credentials")
    auth.login()
    status = auth.status()
    assert status["expires_at"] == 2_000_000_000
    assert status["claims"]["sub"] == "alice"


def test_device_flow_polls_until_authorized(store, discovery):
    messages = []
    discovery.post(DEVICE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dc",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://idp.test/device",
                "verification_uri_complete": "https://idp.test/device?user_code=ABCD-EFGH",
                "interval": 0,
                "expires_in": 60,
            },
        )
    )
    token_route = discovery.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 300}),
        ]
    )
    auth = make_auth(store, flow="device", messages=messages)
    auth.login()
    assert auth.bearer_token() == "at"
    assert token_route.call_count == 3
    assert form(token_route.calls.last.request)["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert "ABCD-EFGH" in messages[0]


def test_device_flow_denied(store, discovery):
    discovery.post(DEVICE_URL).mock(
        return_value=httpx.Response(200, json={"device_code": "dc", "user_code": "X", "interval": 0})
    )
    discovery.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "access_denied"}))
    with pytest.raises(AuthError, match="access_denied"):
        make_auth(store, flow="device").login()


def _browser(params_override=None):
    """A fake browser: follows the authorization URL straight to the redirect URI, like an IdP would."""

    def open_browser(url: str) -> None:
        query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        open_browser.query = query
        response = {"code": "the-code", "state": query["state"], **(params_override or {})}
        target = f"{query['redirect_uri']}?{urlencode(response)}"

        def call() -> None:
            # urllib, not httpx: respx must not intercept the call to the local callback server
            with urllib.request.urlopen(target.replace("localhost", "127.0.0.1"), timeout=5) as r:  # noqa: S310
                r.read()

        threading.Thread(target=call, daemon=True).start()

    open_browser.query = {}
    return open_browser


def test_pkce_login_end_to_end(store, discovery):
    token_route = discovery.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at", "id_token": "it", "expires_in": 300})
    )
    discovery.route(host="127.0.0.1").pass_through()
    browser = _browser()
    auth = make_auth(store, open_browser=browser)
    auth.login()

    query = browser.query
    assert query["response_type"] == "code"
    assert query["client_id"] == "dittoctl"
    assert query["code_challenge_method"] == "S256"
    assert query["audience"] == "ditto"
    assert query["redirect_uri"].startswith("http://localhost:")
    sent = form(token_route.calls.last.request)
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "the-code"
    assert sent["redirect_uri"] == query["redirect_uri"]
    assert code_challenge(sent["code_verifier"]) == query["code_challenge"]
    assert auth.bearer_token() == "at"


def test_pkce_login_rejects_state_mismatch(store, discovery):
    discovery.route(host="127.0.0.1").pass_through()
    auth = make_auth(store, open_browser=_browser({"state": "forged"}))
    with pytest.raises(AuthError, match="state"):
        auth.login()


def test_pkce_login_reports_idp_error(store, discovery):
    discovery.route(host="127.0.0.1").pass_through()
    auth = make_auth(store, open_browser=_browser({"error": "access_denied", "error_description": "user said no"}))
    with pytest.raises(AuthError, match="user said no"):
        auth.login()


def test_logout_forgets_tokens_and_secret(store):
    store.set("prod/oidc-tokens", "{}")
    store.set("prod/client-secret", "s")
    make_auth(store).logout()
    assert store.get("prod/oidc-tokens") is None
    assert store.get("prod/client-secret") is None

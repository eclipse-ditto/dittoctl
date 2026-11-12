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
"""OpenID Connect login.

Supported flows:

* ``pkce``: authorization code with PKCE (RFC 7636) and a loopback redirect (RFC 8252)
* ``device``: device authorization grant (RFC 8628)
* ``client-credentials``: for machine accounts, the client secret is kept in the secret store

Endpoints are found via OIDC discovery (``<issuer>/.well-known/openid-configuration``).
Tokens are kept in the secret store and refreshed with the refresh token when they expire.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from dittoctl.auth.base import AuthProvider, Notify, decode_jwt_claims
from dittoctl.auth.store import SecretStore
from dittoctl.config import Context
from dittoctl.errors import AuthError

CALLBACK_PATH = "/callback"
LOGIN_TIMEOUT_SECONDS = 300
EXPIRY_LEEWAY_SECONDS = 30
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def generate_code_verifier() -> str:
    # 64 random bytes -> 86 characters of the unreserved alphabet, within the 43..128 range of RFC 7636
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass
class TokenSet:
    access_token: str
    issuer: str
    client_id: str
    id_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None

    def expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) >= self.expires_at - EXPIRY_LEEWAY_SECONDS

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> TokenSet:
        return cls(**json.loads(raw))


class _CallbackServer:
    """Loopback HTTP server receiving the authorization response."""

    def __init__(self, port: int) -> None:
        self.result: dict[str, str] | None = None
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                url = urlparse(self.path)
                if url.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                params = {k: v[0] for k, v in parse_qs(url.query).items()}
                server.result = params
                if "error" in params:
                    text = f"Login failed: {html.escape(params.get('error_description') or params['error'])}"
                else:
                    text = "Login complete. You can close this window and return to dittoctl."
                body = f"<!doctype html><title>dittoctl</title><p>{text}</p>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = HTTPServer(("127.0.0.1", port), Handler)
        self.httpd.timeout = 0.5
        self.port = self.httpd.server_address[1]

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.port}{CALLBACK_PATH}"

    def wait(self, timeout: float) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while self.result is None and time.monotonic() < deadline:
            self.httpd.handle_request()
        if self.result is None:
            raise AuthError(f"no login response received within {int(timeout)} seconds")
        return self.result

    def close(self) -> None:
        self.httpd.server_close()


class OidcAuth(AuthProvider):
    method = "oidc"

    def __init__(
        self,
        context: Context,
        store: SecretStore,
        *,
        notify: Notify | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        open_browser: Callable[[str], Any] = webbrowser.open,
    ) -> None:
        super().__init__(context, store, notify=notify)
        self.config = context.auth
        assert self.config.issuer
        assert self.config.client_id
        self.issuer = self.config.issuer.rstrip("/")
        self.client_id = self.config.client_id
        self.http = http or httpx.Client(timeout=context.timeout, verify=context.verify)
        self.sleep = sleep
        self.open_browser = open_browser
        self._discovery: dict[str, Any] | None = None
        self._lock = threading.Lock()

    # --- discovery and token endpoint -------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        if self._discovery is None:
            url = f"{self.issuer}/.well-known/openid-configuration"
            try:
                response = self.http.get(url)
                response.raise_for_status()
                self._discovery = response.json()
            except (httpx.HTTPError, ValueError) as e:
                raise AuthError(f"OIDC discovery failed for {url}: {e}") from e
        return self._discovery

    def _endpoint(self, name: str) -> str:
        endpoint = self.discovery().get(name)
        if not endpoint:
            raise AuthError(f"the OIDC provider {self.issuer} does not announce a {name}")
        return endpoint

    def _client_secret(self) -> str | None:
        return self.store.get(self.secret_key("client-secret"))

    def _client_params(self) -> dict[str, str]:
        params = {"client_id": self.client_id}
        if secret := self._client_secret():
            params["client_secret"] = secret
        return params

    def _token_request(self, data: dict[str, str], previous: TokenSet | None = None) -> TokenSet:
        response = self.http.post(self._endpoint("token_endpoint"), data={**data, **self._client_params()})
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or "access_token" not in body:
            error = body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
            raise AuthError(f"token request to {self.issuer} failed: {error}")
        return self._token_set(body, previous)

    def _token_set(self, body: dict[str, Any], previous: TokenSet | None) -> TokenSet:
        expires_at = None
        if "expires_in" in body:
            expires_at = time.time() + float(body["expires_in"])
        elif claims := decode_jwt_claims(body["access_token"]):
            expires_at = claims.get("exp")
        return TokenSet(
            access_token=body["access_token"],
            issuer=self.issuer,
            client_id=self.client_id,
            id_token=body.get("id_token") or (previous.id_token if previous else None),
            # providers that don't rotate refresh tokens omit them from refresh responses
            refresh_token=body.get("refresh_token") or (previous.refresh_token if previous else None),
            expires_at=expires_at,
        )

    # --- token storage ----------------------------------------------------------------------

    def _load(self) -> TokenSet | None:
        raw = self.store.get(self.secret_key("oidc-tokens"))
        if not raw:
            return None
        try:
            tokens = TokenSet.from_json(raw)
        except (ValueError, TypeError):
            return None
        # tokens from a different issuer or client (the context was edited) are not reused
        if tokens.issuer != self.issuer or tokens.client_id != self.client_id:
            return None
        return tokens

    def _save(self, tokens: TokenSet) -> None:
        self.store.set(self.secret_key("oidc-tokens"), tokens.to_json())

    # --- AuthProvider -----------------------------------------------------------------------

    def _valid_tokens(self, force_refresh: bool = False) -> TokenSet:
        with self._lock:
            tokens = self._load()
            if tokens and not force_refresh and not tokens.expired():
                return tokens
            refresh_error = None
            if tokens and tokens.refresh_token:
                try:
                    tokens = self._token_request(
                        {"grant_type": "refresh_token", "refresh_token": tokens.refresh_token}, tokens
                    )
                    self._save(tokens)
                    return tokens
                except AuthError as e:
                    refresh_error = e  # the refresh token may have expired as well
            if self.config.flow == "client-credentials" and self._client_secret():
                tokens = self._client_credentials()
                self._save(tokens)
                return tokens
            reason = f" (refreshing the token failed: {refresh_error})" if refresh_error else ""
            raise AuthError(
                f"not logged in to context '{self.context.name}' or the session expired{reason}. "
                f"Run 'dittoctl -c {self.context.name} auth login'"
            )

    def bearer_token(self) -> str | None:
        tokens = self._valid_tokens()
        if self.config.use_token == "id":
            if not tokens.id_token:
                raise AuthError("use-token is 'id' but the OIDC provider returned no id token (is 'openid' in scopes?)")
            return tokens.id_token
        return tokens.access_token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token()}"}

    def refresh(self) -> bool:
        try:
            self._valid_tokens(force_refresh=True)
            return True
        except AuthError:
            return False

    def login(self, *, secret: str | None = None, open_browser: bool = True) -> None:
        if secret:
            self.store.set(self.secret_key("client-secret"), secret)
        flow = self.config.flow
        if flow == "pkce":
            tokens = self._pkce_login(open_browser)
        elif flow == "device":
            tokens = self._device_login()
        else:
            if not self._client_secret():
                raise AuthError("the client-credentials flow requires a client secret (--secret-stdin)")
            tokens = self._client_credentials()
        self._save(tokens)

    def logout(self) -> None:
        self.store.delete(self.secret_key("oidc-tokens"))
        self.store.delete(self.secret_key("client-secret"))

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            **super().status(),
            "issuer": self.issuer,
            "client_id": self.client_id,
            "flow": self.config.flow,
        }
        tokens = self._load()
        # without a request to the OIDC provider, a refresh token only promises a new access token
        result["authenticated"] = tokens is not None and (not tokens.expired() or tokens.refresh_token is not None)
        if tokens:
            result["expired"] = tokens.expired()
            result["expires_at"] = tokens.expires_at
            result["refreshable"] = tokens.refresh_token is not None
            token = tokens.id_token if self.config.use_token == "id" else tokens.access_token
            if token and (claims := decode_jwt_claims(token)):
                result["claims"] = claims
        return result

    # --- flows ------------------------------------------------------------------------------

    def _scope(self) -> str:
        return " ".join(self.config.scopes)

    def _pkce_login(self, open_browser: bool) -> TokenSet:
        verifier = generate_code_verifier()
        state = secrets.token_urlsafe(24)
        server = _CallbackServer(self.config.redirect_port)
        try:
            query = {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": server.redirect_uri,
                "scope": self._scope(),
                "state": state,
                "nonce": secrets.token_urlsafe(24),
                "code_challenge": code_challenge(verifier),
                "code_challenge_method": "S256",
                **self.config.extra_params,
            }
            url = f"{self._endpoint('authorization_endpoint')}?{urlencode(query)}"
            self.notify(f"Opening the browser to log in. If it doesn't open, visit:\n{url}")
            if open_browser:
                self.open_browser(url)
            result = server.wait(LOGIN_TIMEOUT_SECONDS)
        finally:
            server.close()
        if "error" in result:
            raise AuthError(f"login failed: {result.get('error_description') or result['error']}")
        if result.get("state") != state:
            raise AuthError("login failed: the state parameter of the response does not match")
        if "code" not in result:
            raise AuthError("login failed: the response contains no authorization code")
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": result["code"],
                "redirect_uri": server.redirect_uri,
                "code_verifier": verifier,
            }
        )

    def _device_login(self) -> TokenSet:
        response = self.http.post(
            self._endpoint("device_authorization_endpoint"),
            data={**self._client_params(), "scope": self._scope(), **self.config.extra_params},
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or "device_code" not in body:
            error = body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
            raise AuthError(f"device authorization request failed: {error}")
        if complete := body.get("verification_uri_complete"):
            self.notify(f"To log in, visit {complete}\n(code: {body.get('user_code')})")
        else:
            self.notify(f"To log in, visit {body.get('verification_uri')} and enter the code {body.get('user_code')}")

        interval = float(body.get("interval", 5))
        deadline = time.monotonic() + float(body.get("expires_in", LOGIN_TIMEOUT_SECONDS))
        data = {"grant_type": DEVICE_GRANT_TYPE, "device_code": body["device_code"]}
        while time.monotonic() < deadline:
            self.sleep(interval)
            response = self.http.post(self._endpoint("token_endpoint"), data={**data, **self._client_params()})
            try:
                token_body = response.json()
            except ValueError:
                token_body = {}
            if response.status_code < 400 and "access_token" in token_body:
                return self._token_set(token_body, None)
            error = token_body.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            reason = token_body.get("error_description") or error or response.status_code
            raise AuthError(f"device login failed: {reason}")
        raise AuthError("device login timed out")

    def _client_credentials(self) -> TokenSet:
        return self._token_request(
            {"grant_type": "client_credentials", "scope": self._scope(), **self.config.extra_params}
        )

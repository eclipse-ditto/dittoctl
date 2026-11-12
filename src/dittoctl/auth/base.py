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
"""Auth providers: turn a context's auth settings into request headers."""

from __future__ import annotations

import base64
import json
import os
import sys
from collections.abc import Callable
from typing import Any, ClassVar

from dittoctl.auth.store import SecretStore
from dittoctl.config import Context
from dittoctl.errors import AuthError

PRE_AUTHENTICATED_HEADER = "x-ditto-pre-authenticated"

Notify = Callable[[str], None]


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def decode_jwt_claims(token: str) -> dict[str, Any] | None:
    """Decode the payload of a JWT without verifying it, for display purposes only."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return None
    return claims if isinstance(claims, dict) else None


class AuthProvider:
    method: ClassVar[str] = "none"

    def __init__(self, context: Context, store: SecretStore, *, notify: Notify | None = None) -> None:
        self.context = context
        self.store = store
        self.notify = notify or _stderr

    def secret_key(self, name: str) -> str:
        return f"{self.context.name}/{name}"

    def headers(self) -> dict[str, str]:
        """Headers to add to every Ditto request. Raises AuthError if credentials are missing."""
        return {}

    def refresh(self) -> bool:
        """Called after a 401. Returns True if new credentials were obtained and the request should be retried."""
        return False

    def login(self, *, secret: str | None = None, open_browser: bool = True) -> None:
        """Obtain and store credentials. ``secret`` is the password, token or client secret, depending on method."""

    def logout(self) -> None:
        """Forget stored credentials."""

    def bearer_token(self) -> str | None:
        """The bearer token sent to Ditto, if this method uses one."""
        return None

    def status(self) -> dict[str, Any]:
        return {"context": self.context.name, "method": self.method, "authenticated": True}


class NoAuth(AuthProvider):
    method = "none"


class PreAuthenticated(AuthProvider):
    """Ditto's pre-authenticated mode: a trusted proxy in front of Ditto sets the subject header."""

    method = "preauth"

    def headers(self) -> dict[str, str]:
        assert self.context.auth.subject
        return {PRE_AUTHENTICATED_HEADER: self.context.auth.subject}

    def status(self) -> dict[str, Any]:
        return {**super().status(), "subject": self.context.auth.subject}


class BasicAuth(AuthProvider):
    method = "basic"

    def _password(self) -> str | None:
        return os.environ.get("DITTOCTL_PASSWORD") or self.store.get(self.secret_key("password"))

    def headers(self) -> dict[str, str]:
        password = self._password()
        if password is None:
            raise AuthError(
                f"no password for context '{self.context.name}'. Run 'dittoctl auth login' or set DITTOCTL_PASSWORD"
            )
        raw = f"{self.context.auth.username}:{password}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}

    def login(self, *, secret: str | None = None, open_browser: bool = True) -> None:
        if not secret:
            raise AuthError("a password is required for basic auth")
        self.store.set(self.secret_key("password"), secret)

    def logout(self) -> None:
        self.store.delete(self.secret_key("password"))

    def status(self) -> dict[str, Any]:
        return {
            **super().status(),
            "username": self.context.auth.username,
            "authenticated": self._password() is not None,
        }


class StaticToken(AuthProvider):
    """A bearer token obtained elsewhere, e.g. from a CI secret."""

    method = "token"

    def bearer_token(self) -> str | None:
        return os.environ.get("DITTOCTL_TOKEN") or self.store.get(self.secret_key("token"))

    def headers(self) -> dict[str, str]:
        token = self.bearer_token()
        if not token:
            raise AuthError(
                f"no token for context '{self.context.name}'. "
                "Run 'dittoctl auth login --token-stdin' or set DITTOCTL_TOKEN"
            )
        return {"Authorization": f"Bearer {token}"}

    def login(self, *, secret: str | None = None, open_browser: bool = True) -> None:
        if not secret:
            raise AuthError("a token is required for token auth")
        self.store.set(self.secret_key("token"), secret)

    def logout(self) -> None:
        self.store.delete(self.secret_key("token"))

    def status(self) -> dict[str, Any]:
        token = self.bearer_token()
        result = {**super().status(), "authenticated": token is not None}
        if token and (claims := decode_jwt_claims(token)):
            result["claims"] = claims
        return result

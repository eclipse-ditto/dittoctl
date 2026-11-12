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
"""Per-invocation state shared by all commands: global options, config, context and client."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click
import httpx

from dittoctl.auth import AuthProvider, provider_for
from dittoctl.auth.store import SecretStore, default_store
from dittoctl.cli import output
from dittoctl.config import AuthConfig, Config, Context
from dittoctl.core.client import DittoClient
from dittoctl.core.curl import redact, to_curl
from dittoctl.errors import AbortedError

ADHOC_CONTEXT = "(url)"


@dataclass
class AppState:
    context_name: str | None = None
    url: str | None = None
    verbose: int = 0
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout: float | None = None
    correlation_id: str | None = None
    config_path: Path | None = None

    _config: Config | None = None
    _store: SecretStore | None = None
    _client: DittoClient | None = None
    _protected_confirmed: bool = False

    def config(self) -> Config:
        if self._config is None:
            self._config = Config.load(self.config_path)
        return self._config

    def store(self) -> SecretStore:
        if self._store is None:
            self._store = default_store()
        return self._store

    def context(self) -> Context:
        """The selected context. ``--url`` without a context gives an ad-hoc context authenticated from env vars."""
        if self.url and not self.context_name:
            return Context(name=ADHOC_CONTEXT, url=self.url.rstrip("/"), auth=_auth_from_env())
        context = self.config().get_context(self.context_name)
        if self.url:
            context.url = self.url.rstrip("/")
        return context

    def auth(self, context: Context | None = None) -> AuthProvider:
        return provider_for(context or self.context(), self.store(), notify=output.info)

    def client(self) -> DittoClient:
        if self._client is None:
            context = self.context()
            self._client = DittoClient(
                context.url,
                self.auth(context),
                headers={**context.headers, **self.extra_headers},
                timeout=self.timeout or context.timeout,
                verify=context.verify,
                correlation_id=self.correlation_id,
                on_request=self._log_request if self.verbose else None,
                on_response=self._log_response if self.verbose > 1 else None,
            )
        return self._client

    def confirm_protected(self, action: str, confirm_context: str | None = None) -> None:
        """Writes to a protected context need its name confirmed: typed at the prompt, or as --confirm-context.

        Under an AI agent (agent mode) they are refused: a person should run such commands. Raises AbortedError.
        """
        context = self.context()
        if not context.protected or self._protected_confirmed:
            return
        name = context.name
        if output.agent_mode():
            raise AbortedError(
                f"context '{name}' is protected, and dittoctl doesn't write to protected contexts in agent mode. "
                "Ask the user to run this command; --dry-run shows what it would do"
            )
        if confirm_context != name:
            if confirm_context is not None or not sys.stdin.isatty():
                raise AbortedError(f"context '{name}' is protected: confirm with --confirm-context {name}")
            if click.prompt(f"Context '{name}' is protected. Type its name to {action}") != name:
                raise AbortedError("context name not confirmed")
        self._protected_confirmed = True

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _log_request(self, request: httpx.Request) -> None:
        output.debug(to_curl(request))

    def _log_response(self, response: httpx.Response) -> None:
        lines = [f"< {response.status_code} {response.reason_phrase}"]
        lines += [f"< {name}: {redact(name, value)}" for name, value in response.headers.items()]
        output.debug("\n".join(lines))


def _auth_from_env() -> AuthConfig:
    if os.environ.get("DITTOCTL_TOKEN"):
        return AuthConfig(method="token")
    if username := os.environ.get("DITTOCTL_USERNAME"):
        return AuthConfig(method="basic", username=username)
    return AuthConfig(method="none")


pass_state = click.make_pass_decorator(AppState)

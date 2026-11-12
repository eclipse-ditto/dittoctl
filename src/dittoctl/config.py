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
"""Contexts: named Ditto endpoints with their auth settings, stored as TOML.

The config file never holds secrets (passwords, tokens, client secrets); those live in the
secret store, see :mod:`dittoctl.auth.store`.

Example::

    current-context = "local"

    [contexts.local]
    url = "http://localhost:8080"

    [contexts.local.auth]
    method = "basic"
    username = "ditto"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

from dittoctl.errors import ConfigError

AUTH_METHODS = ("none", "basic", "token", "preauth", "oidc")
OIDC_FLOWS = ("pkce", "device", "client-credentials")
CONFIG_FILE_NAME = "config.toml"


def config_dir() -> Path:
    if explicit := os.environ.get("DITTOCTL_CONFIG_DIR"):
        return Path(explicit)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "dittoctl"


def state_dir() -> Path:
    if explicit := os.environ.get("DITTOCTL_STATE_DIR"):
        return Path(explicit)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "dittoctl"


def default_config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


@dataclass
class AuthConfig:
    method: str = "none"
    # basic
    username: str | None = None
    # preauth: value of the x-ditto-pre-authenticated header, e.g. "nginx:ditto"
    subject: str | None = None
    # oidc
    issuer: str | None = None
    client_id: str | None = None
    flow: str = "pkce"
    scopes: list[str] = field(default_factory=lambda: ["openid"])
    # added to the authorization and token requests, e.g. {"audience": "ditto"}
    extra_params: dict[str, str] = field(default_factory=dict)
    # 0 picks a free port (RFC 8252 loopback redirect); set a fixed port if the IdP requires an exact redirect URI
    redirect_port: int = 0
    # which token of the token response to send to Ditto: "access" or "id"
    use_token: str = "access"

    def validate(self, context_name: str) -> None:
        where = f"context '{context_name}'"
        if self.method not in AUTH_METHODS:
            expected = ", ".join(AUTH_METHODS)
            raise ConfigError(f"{where}: unknown auth method '{self.method}', expected one of {expected}")
        if self.method == "basic" and not self.username:
            raise ConfigError(f"{where}: auth method 'basic' requires a username")
        if self.method == "preauth" and not self.subject:
            raise ConfigError(f"{where}: auth method 'preauth' requires a subject, e.g. 'nginx:ditto'")
        if self.method == "oidc":
            if not self.issuer or not self.client_id:
                raise ConfigError(f"{where}: auth method 'oidc' requires an issuer and a client id")
            if self.flow not in OIDC_FLOWS:
                raise ConfigError(f"{where}: unknown OIDC flow '{self.flow}', expected one of {', '.join(OIDC_FLOWS)}")
            if self.use_token not in ("access", "id"):
                raise ConfigError(f"{where}: use-token must be 'access' or 'id'")

    def to_toml(self) -> dict[str, Any]:
        data: dict[str, Any] = {"method": self.method}
        if self.method == "basic":
            data["username"] = self.username
        elif self.method == "preauth":
            data["subject"] = self.subject
        elif self.method == "oidc":
            data.update(
                {
                    "issuer": self.issuer,
                    "client-id": self.client_id,
                    "flow": self.flow,
                    "scopes": self.scopes,
                    "use-token": self.use_token,
                }
            )
            if self.extra_params:
                data["extra-params"] = self.extra_params
            if self.redirect_port:
                data["redirect-port"] = self.redirect_port
        return data

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> AuthConfig:
        return cls(
            method=data.get("method", "none"),
            username=data.get("username"),
            subject=data.get("subject"),
            issuer=data.get("issuer"),
            client_id=data.get("client-id"),
            flow=data.get("flow", "pkce"),
            scopes=list(data.get("scopes", ["openid"])),
            extra_params=dict(data.get("extra-params", {})),
            redirect_port=int(data.get("redirect-port", 0)),
            use_token=data.get("use-token", "access"),
        )


@dataclass
class Context:
    name: str
    url: str
    auth: AuthConfig = field(default_factory=AuthConfig)
    namespaces: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    protected: bool = False
    timeout: float = 30.0
    # True, False or the path of a CA bundle
    verify: bool | str = True
    # stream id-only searches via SSE; turn off where the gateway throttles SSE search
    search_streaming: bool = True

    def validate(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ConfigError(f"context '{self.name}': url must start with http:// or https://")
        self.auth.validate(self.name)

    def to_toml(self) -> dict[str, Any]:
        data: dict[str, Any] = {"url": self.url}
        if self.namespaces:
            data["namespaces"] = self.namespaces
        if self.headers:
            data["headers"] = self.headers
        if self.protected:
            data["protected"] = True
        if self.timeout != 30.0:
            data["timeout"] = self.timeout
        if self.verify is not True:
            data["verify"] = self.verify
        if not self.search_streaming:
            data["search-streaming"] = False
        data["auth"] = self.auth.to_toml()
        return data

    @classmethod
    def from_toml(cls, name: str, data: dict[str, Any]) -> Context:
        if "url" not in data:
            raise ConfigError(f"context '{name}' has no url")
        return cls(
            name=name,
            url=str(data["url"]).rstrip("/"),
            auth=AuthConfig.from_toml(data.get("auth", {})),
            namespaces=list(data.get("namespaces", [])),
            headers=dict(data.get("headers", {})),
            protected=bool(data.get("protected", False)),
            timeout=float(data.get("timeout", 30.0)),
            verify=data.get("verify", True),
            search_streaming=bool(data.get("search-streaming", True)),
        )


@dataclass
class Config:
    path: Path
    current_context: str | None = None
    contexts: dict[str, Context] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or default_config_path()
        if not path.exists():
            return cls(path=path)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f"cannot read config file {path}: {e}") from e
        contexts = {name: Context.from_toml(name, ctx) for name, ctx in data.get("contexts", {}).items()}
        return cls(path=path, current_context=data.get("current-context"), contexts=contexts)

    def save(self) -> None:
        data: dict[str, Any] = {}
        if self.current_context:
            data["current-context"] = self.current_context
        data["contexts"] = {name: ctx.to_toml() for name, ctx in sorted(self.contexts.items())}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".toml.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(tomli_w.dumps(data))
        tmp.replace(self.path)

    def get_context(self, name: str | None = None) -> Context:
        name = name or self.current_context
        if not name:
            raise ConfigError(
                "no context selected. Create one with 'dittoctl config add-context', "
                "select one with 'dittoctl config use-context' or pass --url"
            )
        try:
            return self.contexts[name]
        except KeyError:
            known = ", ".join(sorted(self.contexts)) or "none"
            raise ConfigError(f"unknown context '{name}' (known contexts: {known})") from None

    def set_context(self, context: Context) -> None:
        context.validate()
        self.contexts[context.name] = context

    def delete_context(self, name: str) -> Context:
        context = self.get_context(name)
        del self.contexts[name]
        if self.current_context == name:
            self.current_context = None
        return context

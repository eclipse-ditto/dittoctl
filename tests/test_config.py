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
import stat
import sys
from pathlib import Path

import pytest

from dittoctl.auth.store import FileStore
from dittoctl.config import AuthConfig, Config, Context, default_config_path
from dittoctl.errors import ConfigError


def assert_private(path: Path) -> None:
    """Only the owner may read the file. Windows has no POSIX permission bits, so the mode is checked elsewhere."""
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_config_file_gives_empty_config():
    config = Config.load()
    assert config.contexts == {}
    assert config.current_context is None
    assert config.path == default_config_path()


def test_roundtrip_preserves_contexts(tmp_path):
    path = tmp_path / "config.toml"
    config = Config(path=path)
    config.set_context(
        Context(
            name="prod",
            url="https://ditto.example.com",
            auth=AuthConfig(
                method="oidc",
                issuer="https://idp.example.com/realms/iot",
                client_id="dittoctl",
                flow="device",
                scopes=["openid", "offline_access"],
                extra_params={"audience": "ditto"},
                use_token="id",
            ),
            namespaces=["org.example"],
            headers={"x-tenant": "a"},
            protected=True,
            timeout=10.0,
            verify="/etc/ca.pem",
        )
    )
    config.set_context(Context(name="local", url="http://localhost:8080", auth=AuthConfig("basic", username="ditto")))
    config.current_context = "local"
    config.save()

    assert_private(path)
    loaded = Config.load(path)
    assert loaded.current_context == "local"
    assert loaded.contexts == config.contexts


def test_get_context_errors_are_helpful(tmp_path):
    config = Config(path=tmp_path / "c.toml")
    with pytest.raises(ConfigError, match="no context selected"):
        config.get_context()
    config.set_context(Context(name="a", url="http://a"))
    with pytest.raises(ConfigError, match=r"unknown context 'b' \(known contexts: a\)"):
        config.get_context("b")


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (Context(name="x", url="ftp://x"), "url must start"),
        (Context(name="x", url="http://x", auth=AuthConfig("kerberos")), "unknown auth method"),
        (Context(name="x", url="http://x", auth=AuthConfig("basic")), "requires a username"),
        (Context(name="x", url="http://x", auth=AuthConfig("preauth")), "requires a subject"),
        (Context(name="x", url="http://x", auth=AuthConfig("oidc", issuer="https://i")), "requires an issuer"),
        (
            Context(
                name="x", url="http://x", auth=AuthConfig("oidc", issuer="https://i", client_id="c", flow="implicit")
            ),
            "unknown OIDC flow",
        ),
    ],
)
def test_validation(context, message):
    with pytest.raises(ConfigError, match=message):
        context.validate()


def test_delete_current_context_unselects_it(tmp_path):
    config = Config(path=tmp_path / "c.toml")
    config.set_context(Context(name="a", url="http://a"))
    config.current_context = "a"
    config.delete_context("a")
    assert config.current_context is None
    assert config.contexts == {}


def test_broken_toml_is_reported(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("contexts = [", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot read config file"):
        Config.load(path)


def test_file_store(tmp_path):
    store = FileStore(tmp_path / "s" / "secrets.json")
    assert store.get("a/password") is None
    store.set("a/password", "pw")
    store.set("b/token", "t")
    assert store.get("a/password") == "pw"
    assert_private(store.path)
    store.delete("a/password")
    store.delete("does-not-exist")
    assert store.get("a/password") is None
    assert store.get("b/token") == "t"

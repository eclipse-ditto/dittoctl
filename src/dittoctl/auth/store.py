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
"""Secret storage: the OS keyring, with a 0600 file in the state directory as fallback.

Select the backend with ``DITTOCTL_SECRET_STORE=keyring|file|auto`` (default ``auto``).
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Protocol

from dittoctl.config import state_dir
from dittoctl.errors import ConfigError

KEYRING_SERVICE = "dittoctl"


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...


class KeyringStore:
    def __init__(self, service: str = KEYRING_SERVICE) -> None:
        self.service = service

    def get(self, key: str) -> str | None:
        import keyring

        return keyring.get_password(self.service, key)

    def set(self, key: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service, key, value)

    def delete(self, key: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        with contextlib.suppress(PasswordDeleteError):
            keyring.delete_password(self.service, key)


class FileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_dir() / "secrets.json"

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"cannot read secret file {self.path}: {e}") from e

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        tmp.replace(self.path)

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    def delete(self, key: str) -> None:
        data = self._read()
        if data.pop(key, None) is not None:
            self._write(data)


def _keyring_usable() -> bool:
    try:
        import keyring
        from keyring.backends import fail

        return not isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return False


def default_store() -> SecretStore:
    backend = os.environ.get("DITTOCTL_SECRET_STORE", "auto")
    if backend == "file":
        return FileStore()
    if backend == "keyring":
        return KeyringStore()
    if backend != "auto":
        raise ConfigError(f"DITTOCTL_SECRET_STORE must be 'keyring', 'file' or 'auto', not '{backend}'")
    return KeyringStore() if _keyring_usable() else FileStore()

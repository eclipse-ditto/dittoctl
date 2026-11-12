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
from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass

import pytest

from dittoctl.cli.main import main


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Keep tests away from the real config, keyring, DITTOCTL_* variables and agent detection."""
    for key in list(os.environ):
        if key.startswith("DITTOCTL_") or key in ("CLAUDECODE", "AI_AGENT"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("DITTOCTL_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DITTOCTL_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DITTOCTL_SECRET_STORE", "file")


@dataclass
class Result:
    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture
def run(capsys, monkeypatch):
    def _run(*args: str, stdin: str | None = None) -> Result:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin or ""))
        code = main(list(args))
        out, err = capsys.readouterr()
        return Result(int(code), out, err)

    return _run

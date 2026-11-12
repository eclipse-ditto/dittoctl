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
"""Render requests as equivalent curl commands for ``--verbose``."""

from __future__ import annotations

import shlex

import httpx

SENSITIVE_HEADERS = {"authorization", "cookie", "x-ditto-pre-authenticated"}
SKIPPED_HEADERS = {"host", "content-length", "accept-encoding", "connection", "user-agent"}


def redact(name: str, value: str) -> str:
    if name.lower() not in SENSITIVE_HEADERS:
        return value
    scheme, _, _ = value.partition(" ")
    return f"{scheme} ***" if scheme.lower() in ("bearer", "basic") else "***"


def to_curl(request: httpx.Request, *, redact_secrets: bool = True) -> str:
    parts = ["curl", "-X", request.method, shlex.quote(str(request.url))]
    # raw headers keep the original spelling, items() would lowercase the names
    for raw_name, raw_value in request.headers.raw:
        name, value = raw_name.decode("latin-1"), raw_value.decode("latin-1")
        if name.lower() in SKIPPED_HEADERS:
            continue
        shown = redact(name, value) if redact_secrets else value
        parts += ["-H", shlex.quote(f"{name}: {shown}")]
    content = request.content
    if content:
        try:
            body = content.decode("utf-8")
        except UnicodeDecodeError:
            body = f"<{len(content)} bytes>"
        parts += ["--data-raw", shlex.quote(body)]
    return " ".join(parts)

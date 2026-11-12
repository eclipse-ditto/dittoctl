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
"""Connections. See https://eclipse.dev/ditto/connectivity-manage-connections.html"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from dittoctl.core.client import DittoClient, DittoResponse

CONNECTIONS_PATH = "/api/2/connections"
COMMANDS = {
    "open": "connectivity.commands:openConnection",
    "close": "connectivity.commands:closeConnection",
    "reset-metrics": "connectivity.commands:resetConnectionMetrics",
    "enable-logs": "connectivity.commands:enableConnectionLogs",
    "reset-logs": "connectivity.commands:resetConnectionLogs",
}


def connection_path(connection_id: str, *parts: str) -> str:
    return f"{CONNECTIONS_PATH}/{quote(connection_id, safe='')}" + "".join(f"/{p}" for p in parts)


def send_command(client: DittoClient, connection_id: str, command: str) -> DittoResponse:
    """Send one of :data:`COMMANDS` (by its short name) to a connection."""
    return client.post(connection_path(connection_id, "command"), content=COMMANDS[command], content_type="text/plain")


def redact_uri(uri: str) -> str:
    """``amqps://user:secret@host:5671`` becomes ``amqps://user:***@host:5671``."""
    try:
        parts = urlsplit(uri)
    except ValueError:
        return uri
    if not parts.password:
        return uri
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    return urlunsplit(parts._replace(netloc=f"{parts.username}:***@{host}"))


_AUTH_HEADER = re.compile(r"(?i)(authorization\"?\s*[=:]\s*\"?)(basic|bearer)\s+[A-Za-z0-9+/=._~-]+")
_URI_PASSWORD = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@\s]+@")


def redact_secrets(text: str) -> str:
    """Mask Authorization header values and passwords in URIs within a text, e.g. a connection log message:
    Ditto's connection logs include the headers of the request that caused a message."""
    return _URI_PASSWORD.sub(r"\1***@", _AUTH_HEADER.sub(r"\1\2 ***", text))


def log_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Identifies a connection log entry, to show each entry only once when following the logs."""
    return tuple(entry.get(k) for k in ("timestamp", "correlationId", "category", "type", "address", "message"))

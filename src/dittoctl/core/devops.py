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
"""DevOps commands: log levels, runtime config, piggyback commands, search reindexing, namespace erasure, status.

See https://eclipse.dev/ditto/installation-operating.html#devops-commands
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from dittoctl.core.client import DittoClient, DittoResponse
from dittoctl.errors import DittoctlError

LOGGING_PATH = "/devops/logging"
CONFIG_PATH = "/devops/config"
PIGGYBACK_PATH = "/devops/piggyback"
PUB_SUB_MEDIATOR = "/system/distributedPubSubMediator"
BACKGROUND_SYNC = "/user/thingsWildcardSearchRoot/searchUpdaterRoot/backgroundSyncProxy"
THINGS_UPDATER = "/user/thingsWildcardSearchRoot/searchUpdaterRoot/thingsUpdater"
# the service name of the search service in piggyback paths ("things-search" in log level responses)
SEARCH_SERVICE = "search"


def _path(base: str, *segments: str | None) -> str:
    return base + "".join(f"/{quote(s, safe='')}" for s in segments if s)


def get_logging(client: DittoClient, service: str | None = None) -> Any:
    return client.get(_path(LOGGING_PATH, service)).body


def set_logging(client: DittoClient, logger: str, level: str, service: str | None = None) -> Any:
    return client.put(_path(LOGGING_PATH, service), json={"logger": logger, "level": level.lower()}).body


def get_config(
    client: DittoClient, service: str | None = None, instance: str | None = None, path: str | None = None
) -> Any:
    params = {"path": path} if path else None
    return client.get(_path(CONFIG_PATH, service, instance if service else None), params=params).body


def duration_seconds(value: str) -> float:
    """Ditto duration strings: ``500ms``, ``10s``, ``2m``, ``1h``, or plain seconds."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*", value)
    if not match:
        raise DittoctlError(f"invalid duration '{value}', expected e.g. 500ms, 10s, 2m")
    number, unit = float(match.group(1)), match.group(2) or "s"
    return number * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]


def piggyback(
    client: DittoClient,
    command: dict[str, Any],
    *,
    service: str | None = None,
    instance: str | None = None,
    timeout: str = "10s",
) -> DittoResponse:
    """Send a piggyback command (``{"targetActorSelection": ..., "headers": ..., "piggybackCommand": ...}``)."""
    return client.post(
        _path(PIGGYBACK_PATH, service, instance if service else None),
        json=command,
        params={"timeout": timeout},
        raise_for_status=False,
        retry=False,
        # the HTTP request has to outlive the time Ditto waits for the responses
        timeout=duration_seconds(timeout) + 15,
    )


def reindex_command(namespaces: Sequence[str] | None = None) -> dict[str, Any]:
    """Force the next background sync to update the search index of all things (or of the given namespaces)."""
    headers: dict[str, Any] = {"aggregate": False, "is-group-topic": False, "force-update": True}
    if namespaces:
        headers["namespaces"] = list(namespaces)
    return {
        "targetActorSelection": BACKGROUND_SYNC,
        "headers": headers,
        "piggybackCommand": {"type": "common.commands:shutdown"},
    }


def reindex_thing_command(thing_id: str) -> dict[str, Any]:
    """Update the search index entry of one thing immediately."""
    return {
        "targetActorSelection": THINGS_UPDATER,
        "headers": {"aggregate": False, "is-group-topic": True},
        "piggybackCommand": {"type": "thing-search.sudo.commands:sudoUpdateThing", "thingId": thing_id},
    }


def block_namespace_command(namespace: str) -> dict[str, Any]:
    return {
        "targetActorSelection": PUB_SUB_MEDIATOR,
        "headers": {"aggregate": False},
        "piggybackCommand": {"type": "namespaces.commands:blockNamespace", "namespace": namespace},
    }


def shutdown_namespace_command(namespace: str) -> dict[str, Any]:
    # Ditto requires the headers field, although the documented example leaves it out
    return {
        "targetActorSelection": PUB_SUB_MEDIATOR,
        "headers": {"aggregate": False},
        "piggybackCommand": {
            "type": "common.commands:shutdown",
            "reason": {"type": "purge-namespace", "details": namespace},
        },
    }


def purge_namespace_command(namespace: str) -> dict[str, Any]:
    return {
        "targetActorSelection": PUB_SUB_MEDIATOR,
        "headers": {"aggregate": True, "is-group-topic": True},
        "piggybackCommand": {"type": "namespaces.commands:purgeNamespace", "namespace": namespace},
    }


def unblock_namespace_command(namespace: str) -> dict[str, Any]:
    return {
        "targetActorSelection": PUB_SUB_MEDIATOR,
        "headers": {"aggregate": False},
        "piggybackCommand": {"type": "namespaces.commands:unblockNamespace", "namespace": namespace},
    }


def purge_results(body: Any) -> list[dict[str, Any]]:
    """The per-resource-type results of a purgeNamespace response (nested under arbitrary keys)."""
    results: list[dict[str, Any]] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "namespaces.responses:purgeNamespace":
                results.append(value)
            else:
                for child in value.values():
                    collect(child)

    collect(body)
    return results


def piggyback_errors(body: Any) -> list[dict[str, Any]]:
    """The error responses in a piggyback answer: the answer itself, or (aggregated) those of single instances.

    Ditto answers HTTP 200 even if the addressed actors failed, e.g. with ``devops.responses:errorResponse``.
    """
    if not isinstance(body, dict):
        return []
    status = body.get("status")
    if isinstance(status, int) and status >= 400:
        return [body]
    return [error for child in body.values() for error in piggyback_errors(child)]


def purge_succeeded(result: dict[str, Any]) -> bool:
    """Ditto 3.9 reports success as status 200; the docs show a ``successful`` flag, which is honored if present."""
    return bool(result.get("successful", result.get("status") == 200))


def health_lines(node: dict[str, Any], depth: int = 0) -> list[tuple[int, str, str]]:
    """Flatten Ditto's health tree (``/status/health``) into (depth, label, status) rows."""
    rows = [(depth, str(node.get("label", "")), str(node.get("status", "")))]
    for child in node.get("children", []):
        rows.extend(health_lines(child, depth + 1))
    return rows

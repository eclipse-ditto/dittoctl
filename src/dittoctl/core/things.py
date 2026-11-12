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
"""Reading things: single retrieve, retrieve by ids, history and the change stream."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import quote

from dittoctl.core.client import DittoClient, DittoResponse
from dittoctl.core.conditions import Conditions
from dittoctl.core.sse import iter_sse
from dittoctl.errors import DittoError

THINGS_PATH = "/api/2/things"
# conservative: keeps GET /api/2/things?ids=... well below common URL length limits
IDS_BATCH_CHARS = 1500


def thing_path(thing_id: str, path: str | None = None) -> str:
    """The API path of a thing or of a JSON pointer within it, with each segment URL-encoded."""
    result = f"{THINGS_PATH}/{quote(thing_id, safe=':')}"
    segments = [quote(s, safe=":") for s in (path or "").split("/") if s]
    return result + "".join(f"/{s}" for s in segments)


def get_thing(
    client: DittoClient,
    thing_id: str,
    *,
    path: str | None = None,
    fields: str | None = None,
    at_revision: int | None = None,
    at_timestamp: str | None = None,
    live: bool = False,
    live_timeout: int | None = None,
    conditions: Conditions | None = None,
) -> DittoResponse:
    """Retrieve a thing (or a path within it), optionally as it was at a historical revision or timestamp.

    ``live`` asks the device itself (Ditto's live channel) instead of the twin; combine it with the
    ``live_condition`` and ``live_timeout_strategy`` conditions to fall back to the twin.
    """
    headers: dict[str, str] = {}
    if at_revision is not None:
        headers["at-historical-revision"] = str(at_revision)
    if at_timestamp:
        headers["at-historical-timestamp"] = at_timestamp
    params: dict[str, str] = {"fields": fields} if fields else {}
    if live:
        params["channel"] = "live"
        if live_timeout:
            params["timeout"] = f"{live_timeout}s"
    return client.get(thing_path(thing_id, path), params=params, headers=headers, conditions=conditions)


def _id_batches(thing_ids: Sequence[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    length = 0
    for thing_id in thing_ids:
        if batch and length + len(thing_id) + 1 > IDS_BATCH_CHARS:
            yield batch
            batch, length = [], 0
        batch.append(thing_id)
        length += len(thing_id) + 1
    if batch:
        yield batch


def get_things(client: DittoClient, thing_ids: Sequence[str], *, fields: str | None = None) -> Iterator[dict[str, Any]]:
    """Retrieve several things by id, in batches. Things that don't exist or aren't visible are left out."""
    for batch in _id_batches(thing_ids):
        params = {"ids": ",".join(batch)}
        if fields:
            params["fields"] = fields
        body = client.get(THINGS_PATH, params=params).body
        yield from body or []


def watch_things(
    client: DittoClient,
    *,
    rql_filter: str | None = None,
    namespaces: Sequence[str] | None = None,
    thing_ids: Sequence[str] | None = None,
    fields: str | None = None,
    extra_fields: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Follow the server-sent event stream of thing changes. See https://eclipse.dev/ditto/httpapi-sse.html"""
    params: dict[str, str] = {}
    if rql_filter:
        params["filter"] = rql_filter
    if namespaces:
        params["namespaces"] = ",".join(namespaces)
    if thing_ids:
        params["ids"] = ",".join(thing_ids)
    if fields:
        params["fields"] = fields
    if extra_fields:
        params["extraFields"] = extra_fields
    with client.stream("GET", THINGS_PATH, params=params, headers={"Accept": "text/event-stream"}) as response:
        for event in iter_sse(response.iter_lines()):
            if event.data.strip():
                yield json.loads(event.data)


def thing_history(
    client: DittoClient,
    thing_id: str,
    *,
    from_revision: int | None = None,
    to_revision: int | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    fields: str | None = None,
    rql_filter: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream the changes of a thing per revision, i.e. its historical events (needs history retention in Ditto).

    Revisions may be negative to count back from the current one. See https://eclipse.dev/ditto/basic-history.html
    """
    params: dict[str, str] = {}
    for name, value in (
        ("from-historical-revision", from_revision),
        ("to-historical-revision", to_revision),
        ("from-historical-timestamp", from_time),
        ("to-historical-timestamp", to_time),
        ("fields", fields),
        ("filter", rql_filter),
    ):
        if value is not None:
            params[name] = str(value)
    path = thing_path(thing_id)
    with client.stream("GET", path, params=params, headers={"Accept": "text/event-stream"}) as response:
        for event in iter_sse(response.iter_lines()):
            if not event.data.strip():
                continue
            item = json.loads(event.data)
            if DittoError.is_error_body(item) and "thingId" not in item:
                raise DittoError.from_body(item["status"], item, response.headers.get("correlation-id"))
            yield item


def thing_description(client: DittoClient, thing_id: str, feature: str | None = None) -> Any:
    """The WoT Thing Description Ditto generates from the thing's (or feature's) definition."""
    path = thing_path(thing_id, f"features/{feature}" if feature else None)
    return client.get(path, headers={"Accept": "application/td+json"}).body


def wot_directory(client: DittoClient) -> Any:
    """Ditto's WoT Thing Directory (``/.well-known/wot``, Ditto 3.9+)."""
    return client.get("/.well-known/wot", headers={"Accept": "application/td+json"}).body

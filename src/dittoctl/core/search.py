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
"""Things search: cursor paging and SSE streaming. See https://eclipse.dev/ditto/httpapi-search.html

Paging is the default. Ditto streams search results via SSE by retrieving each thing with its own
command, which is about 4x slower and more expensive for Ditto than the batched retrieval of a page
as soon as any field besides ``thingId`` is selected. With only ``thingId`` no retrieval is needed and
SSE is about twice as fast (measured with Ditto 3.9, see PLAN.md). :func:`find_things` picks accordingly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from enum import StrEnum
from typing import Any

import httpx

from dittoctl.core.client import DittoClient, DittoResponse
from dittoctl.core.sse import iter_sse
from dittoctl.errors import DittoctlError, DittoError

SEARCH_PATH = "/api/2/search/things"
COUNT_PATH = "/api/2/search/things/count"
MAX_PAGE_SIZE = 200
# above this length the query goes into a form-encoded POST body instead of the URL
POST_THRESHOLD = 2000
# Ditto ends idle search streams after 60s by default (gateway streaming.search-idle-timeout)
STREAM_READ_TIMEOUT = 90.0
STREAM_RECONNECTS = 3


class Transport(StrEnum):
    AUTO = "auto"
    PAGING = "paging"
    SSE = "sse"


def sort_option(sort: str | Sequence[str] | None) -> str | None:
    """Turn ``-_modified,attributes/name`` (or a list of keys) into ``sort(-_modified,+attributes/name)``."""
    if not sort:
        return None
    keys = sort.split(",") if isinstance(sort, str) else list(sort)
    normalized = []
    for key in (k.strip() for k in keys):
        if not key:
            continue
        normalized.append(key if key[0] in "+-" else f"+{key}")
    return f"sort({','.join(normalized)})" if normalized else None


def _query(client: DittoClient, path: str, params: dict[str, Any]) -> DittoResponse:
    length = sum(len(str(v)) for v in params.values())
    if length > POST_THRESHOLD:
        # searching is read-only, so the POST can be retried like a GET
        return client.post(path, data={k: str(v) for k, v in params.items()}, retry=True)
    return client.get(path, params=params)


def _base_params(rql_filter: str | None, namespaces: Sequence[str] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if rql_filter:
        params["filter"] = rql_filter
    if namespaces:
        params["namespaces"] = ",".join(namespaces)
    return params


def search_things(
    client: DittoClient,
    *,
    rql_filter: str | None = None,
    namespaces: Sequence[str] | None = None,
    fields: str | None = None,
    sort: str | Sequence[str] | None = None,
    limit: int | None = None,
    page_size: int = MAX_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Yield all things matching the filter, following the search cursor page by page."""
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise DittoctlError(f"page size must be between 1 and {MAX_PAGE_SIZE}")
    if limit is not None and limit < 1:
        return
    size = min(page_size, limit) if limit else page_size
    params = _base_params(rql_filter, namespaces)
    if fields:
        params["fields"] = fields
    sort_part = sort_option(sort)
    cursor: str | None = None
    yielded = 0
    while True:
        option = [f"size({size})"]
        if sort_part:
            option.append(sort_part)
        if cursor:
            option.append(f"cursor({cursor})")
        body = _query(client, SEARCH_PATH, {**params, "option": ",".join(option)}).body
        if not isinstance(body, dict):
            raise DittoctlError(f"unexpected search response: {body!r}")
        for item in body.get("items", []):
            yield item
            yielded += 1
            if limit and yielded >= limit:
                return
        cursor = body.get("cursor")
        if not cursor:
            return


def stream_things(
    client: DittoClient,
    *,
    rql_filter: str | None = None,
    namespaces: Sequence[str] | None = None,
    fields: str | None = None,
    sort: str | Sequence[str] | None = None,
    limit: int | None = None,
    max_reconnects: int = STREAM_RECONNECTS,
) -> Iterator[dict[str, Any]]:
    """Yield the things matching the filter from Ditto's SSE search stream.

    A dropped connection is resumed after the last received thing via ``Last-Event-ID``. Errors arrive as
    events with a Ditto error body (the HTTP status is already 200 then) and are raised as :class:`DittoError`.
    """
    if limit is not None and limit < 1:
        return
    params = _base_params(rql_filter, namespaces)
    if fields:
        params["fields"] = fields
    if sort_part := sort_option(sort):
        params["option"] = sort_part
    last_id: str | None = None
    yielded = 0
    reconnects = 0
    while True:
        headers = {"Accept": "text/event-stream"}
        if last_id:
            headers["Last-Event-ID"] = last_id
        try:
            with client.stream(
                "GET", SEARCH_PATH, params=params, headers=headers, read_timeout=STREAM_READ_TIMEOUT
            ) as response:
                for event in iter_sse(response.iter_lines()):
                    if not event.data.strip():
                        continue
                    item = json.loads(event.data)
                    if DittoError.is_error_body(item) and "thingId" not in item:
                        raise DittoError.from_body(item["status"], item, response.headers.get("correlation-id"))
                    yield item
                    yielded += 1
                    last_id = event.id or item.get("thingId") or last_id
                    if limit and yielded >= limit:
                        return
            return
        except httpx.TransportError as e:
            if reconnects >= max_reconnects:
                raise DittoctlError(f"search stream failed after {reconnects} reconnects: {e}") from e
            client.sleep(client.backoff * 2**reconnects)
            reconnects += 1


def choose_transport(
    transport: Transport, *, fields: str | None, rql_filter: str | None, streaming_allowed: bool
) -> Transport:
    """Resolve ``auto``: SSE for id-only searches whose filter fits into a URL, if the context allows it."""
    if transport != Transport.AUTO:
        return transport
    ids_only = fields is not None and fields.replace(" ", "") == "thingId"
    fits_url = len(rql_filter or "") <= POST_THRESHOLD
    return Transport.SSE if ids_only and streaming_allowed and fits_url else Transport.PAGING


def find_things(
    client: DittoClient,
    *,
    rql_filter: str | None = None,
    namespaces: Sequence[str] | None = None,
    fields: str | None = None,
    sort: str | Sequence[str] | None = None,
    limit: int | None = None,
    page_size: int = MAX_PAGE_SIZE,
    transport: Transport = Transport.AUTO,
    streaming_allowed: bool = True,
) -> Iterator[dict[str, Any]]:
    """Search things with the cheaper transport, or the one asked for.

    ``auto`` streams via SSE when only thing ids are requested and ``streaming_allowed`` (contexts can turn it
    off, e.g. when the gateway throttles SSE search) and the filter fits into a URL; otherwise it pages.
    """
    transport = choose_transport(transport, fields=fields, rql_filter=rql_filter, streaming_allowed=streaming_allowed)
    if transport == Transport.SSE:
        return stream_things(
            client, rql_filter=rql_filter, namespaces=namespaces, fields=fields, sort=sort, limit=limit
        )
    return search_things(
        client, rql_filter=rql_filter, namespaces=namespaces, fields=fields, sort=sort, limit=limit, page_size=page_size
    )


def count_things(client: DittoClient, *, rql_filter: str | None = None, namespaces: Sequence[str] | None = None) -> int:
    body = _query(client, COUNT_PATH, _base_params(rql_filter, namespaces)).body
    try:
        return int(body)
    except (TypeError, ValueError):
        raise DittoctlError(f"unexpected count response: {body!r}") from None

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
"""Selecting the things a command acts on: explicit ids, an id file, or an RQL filter."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from dittoctl.core.client import DittoClient
from dittoctl.core.search import Transport, choose_transport, count_things, find_things
from dittoctl.errors import DittoctlError

_SEPARATORS = re.compile(r"[\t,;\s]")


def read_ids(lines: Iterable[str]) -> list[str]:
    """Thing ids from lines of text: the first column of each line, skipping blank lines and ``#`` comments.

    The first column is taken so that files written with ``--failed-out`` (id, status, error, ...) can be
    passed back as ``--ids-file`` directly.
    """
    ids = []
    for line in lines:
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        ids.append(_SEPARATORS.split(line, maxsplit=1)[0])
    return ids


def read_ids_file(path: str) -> list[str]:
    if path == "-":
        return read_ids(sys.stdin)
    try:
        with open(path, encoding="utf-8") as f:
            return read_ids(f)
    except OSError as e:
        raise DittoctlError(f"cannot read ids file {path}: {e}") from e


def unique(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


@dataclass
class Selection:
    ids: Sequence[str] = ()
    ids_file: str | None = None
    rql_filter: str | None = None
    namespaces: Sequence[str] = field(default_factory=list)
    include_file: str | None = None
    exclude_file: str | None = None

    def describe(self) -> str:
        if self.rql_filter:
            where = f" in {', '.join(self.namespaces)}" if self.namespaces else ""
            return f"things matching {self.rql_filter}{where}"
        return "the given things"


def _select_by_filter(
    client: DittoClient, selection: Selection, streaming_allowed: bool, warn: Callable[[str], None]
) -> list[str]:
    def ids_via(transport: Transport) -> list[str]:
        found = find_things(
            client,
            rql_filter=selection.rql_filter,
            namespaces=selection.namespaces,
            fields="thingId",
            sort="+thingId",
            transport=transport,
        )
        return unique(item["thingId"] for item in found if "thingId" in item)

    transport = choose_transport(
        Transport.AUTO, fields="thingId", rql_filter=selection.rql_filter, streaming_allowed=streaming_allowed
    )
    ids = ids_via(transport)
    if transport == Transport.SSE:
        # Ditto can end an SSE search stream early without an error event, e.g. when a search node fails
        # mid-stream. A selection for writes must be complete, so check it against the count.
        expected = count_things(client, rql_filter=selection.rql_filter, namespaces=selection.namespaces)
        if len(ids) < expected:
            warn(f"the SSE search stream returned {len(ids)} of {expected} things; selecting again with paging")
            ids = ids_via(Transport.PAGING)
    return ids


def resolve(
    client: DittoClient,
    selection: Selection,
    *,
    streaming_allowed: bool = True,
    warn: Callable[[str], None] = lambda _m: None,
) -> list[str]:
    """The ids of the selected things, without duplicates, in a stable order."""
    explicit = list(selection.ids)
    if selection.ids_file:
        explicit += read_ids_file(selection.ids_file)
    has_ids = bool(selection.ids) or selection.ids_file is not None
    if has_ids and selection.rql_filter:
        raise DittoctlError("select things either by id (arguments, --ids-file) or by --filter, not both")
    if not has_ids and not selection.rql_filter:
        raise DittoctlError("no things selected: pass thing ids, --ids-file or --filter")
    ids = unique(explicit) if has_ids else _select_by_filter(client, selection, streaming_allowed, warn)
    if selection.include_file:
        include = set(read_ids_file(selection.include_file))
        ids = [i for i in ids if i in include]
    if selection.exclude_file:
        exclude = set(read_ids_file(selection.exclude_file))
        ids = [i for i in ids if i not in exclude]
    return ids

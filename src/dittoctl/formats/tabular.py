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
"""CSV and table output with column discovery."""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import chain, islice
from typing import Any, TextIO

from rich.console import Console
from rich.table import Table

from dittoctl.formats.flatten import cell, flatten, get_path, short_headers

_ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def excel_timestamp(value: str) -> str:
    """``2026-11-06T15:19:54.123Z`` becomes ``2026-11-06 15:19:54`` (UTC), which Excel recognizes as a date."""
    if not _ISO_TIMESTAMP.match(value):
        return value
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Columns:
    """Column selection: explicit paths, or discovered from the first ``discover_rows`` rows (0: all rows)."""

    explicit: Sequence[str] | None = None
    discover_rows: int = 100
    short: bool = False


class _ColumnResolver:
    def __init__(self, columns: Columns, warn: Callable[[str], None]) -> None:
        self.columns = columns
        self.warn = warn
        self.paths: list[str] = []
        self._known: set[str] = set()
        self._warned: set[str] = set()

    def resolve(self, items: Iterable[Any]) -> Iterator[Any]:
        """Determine the columns; returns an iterator over all items (buffered ones first)."""
        iterator = iter(items)
        if self.columns.explicit:
            self.paths = list(self.columns.explicit)
            return iterator
        limit = self.columns.discover_rows
        buffered = list(iterator) if limit <= 0 else list(islice(iterator, limit))
        for item in buffered:
            for path in flatten(item):
                if path not in self._known:
                    self._known.add(path)
                    self.paths.append(path)
        return chain(buffered, iterator)

    def row(self, item: Any) -> list[Any]:
        if self.columns.explicit:
            # explicit columns may name a parent object, so look the paths up in the nested item
            return [get_path(item, path) for path in self.paths]
        flat = flatten(item)
        unknown = flat.keys() - self._known - self._warned
        if unknown:
            self._warned.update(unknown)
            names = ", ".join(sorted(unknown)[:5]) + (" …" if len(unknown) > 5 else "")
            self.warn(
                f"column(s) {names} first appeared after the first {self.columns.discover_rows} rows and are left "
                "out; pass --discover-rows 0 or --columns"
            )
        return [flat.get(path) for path in self.paths]

    def headers(self) -> list[str]:
        if not self.columns.short:
            return list(self.paths)
        mapping = short_headers(self.paths)
        return [mapping[p] for p in self.paths]


def write_csv(
    items: Iterable[Any],
    out: TextIO,
    *,
    columns: Columns | None = None,
    delimiter: str = ",",
    header: bool = True,
    excel: bool = False,
    warn: Callable[[str], None] = lambda _m: None,
) -> int:
    """Stream items as CSV rows; only the discovery window is held in memory. Returns the number of rows."""
    resolver = _ColumnResolver(columns or Columns(), warn)
    remaining = resolver.resolve(items)
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    if header:
        writer.writerow(resolver.headers())
    count = 0
    for item in remaining:
        values = [cell(v) for v in resolver.row(item)]
        if excel:
            values = [excel_timestamp(v) for v in values]
        writer.writerow(values)
        count += 1
    return count


def print_table(
    items: Iterable[Any],
    console: Console,
    *,
    columns: Columns | None = None,
    warn: Callable[[str], None] = lambda _m: None,
) -> int:
    """Render items as a table. All rows are collected first, so use CSV or NDJSON for large results."""
    columns = columns or Columns(discover_rows=0)
    resolver = _ColumnResolver(columns, warn)
    rows = [resolver.row(item) for item in resolver.resolve(items)]
    table = Table(box=None, pad_edge=False, header_style="bold")
    for name in resolver.headers():
        table.add_column(name, overflow="fold")
    for row in rows:
        table.add_row(*(cell(v) for v in row))
    console.print(table)
    return len(rows)

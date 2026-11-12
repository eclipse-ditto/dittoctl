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
"""Writing streams of JSON items in the output formats: table, json, ndjson, csv, ids."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, TextIO

from rich.console import Console
from rich.highlighter import JSONHighlighter
from rich.text import Text

from dittoctl.formats.tabular import Columns, print_table, write_csv

ITEM_FORMATS = ("table", "json", "ndjson", "csv", "ids")


def json_writer(out: TextIO) -> Callable[[str], Any]:
    """``out.write``, but on a terminal with JSON syntax highlighting, as for single JSON documents."""
    if not out.isatty():
        return out.write
    console = Console(file=out, emoji=False, markup=False, highlight=False, soft_wrap=True)
    highlight = JSONHighlighter()
    return lambda text: console.print(highlight(Text(text)), end="")


def write_json_array(items: Iterable[Any], out: TextIO, *, compact: bool = False) -> int:
    """A JSON array, written item by item: pretty-printed, or on a single line with ``compact``."""
    write = json_writer(out)
    count = 0
    write("[")
    for item in items:
        if compact:
            write(("," if count else "") + json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        else:
            write(",\n" if count else "\n")
            text = json.dumps(item, indent=2, ensure_ascii=False)
            write("\n".join("  " + line for line in text.splitlines()))
        count += 1
    write("]\n" if compact or not count else "\n]\n")
    return count


def write_ndjson(items: Iterable[Any], out: TextIO, *, flush: bool = False) -> int:
    write = json_writer(out)
    count = 0
    for item in items:
        write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        if flush:
            out.flush()
        count += 1
    return count


def write_ids(items: Iterable[Any], out: TextIO, key: str = "thingId") -> int:
    count = 0
    for item in items:
        if isinstance(item, dict) and key in item:
            out.write(f"{item[key]}\n")
            count += 1
    return count


def write_items(
    items: Iterable[Any],
    fmt: str,
    out: TextIO,
    *,
    columns: Columns | None = None,
    delimiter: str = ",",
    header: bool = True,
    excel: bool = False,
    compact: bool = False,
    warn: Callable[[str], None] = lambda _m: None,
) -> int:
    """Write items in the given format and return how many were written; ``compact`` puts a JSON array on one line."""
    if fmt == "json":
        return write_json_array(items, out, compact=compact)
    if fmt == "ndjson":
        return write_ndjson(items, out)
    if fmt == "ids":
        return write_ids(items, out)
    if fmt == "csv":
        return write_csv(items, out, columns=columns, delimiter=delimiter, header=header, excel=excel, warn=warn)
    if fmt == "table":
        # on a terminal the table fits its width; elsewhere (pipes, files) lines are never wrapped
        width = None if out.isatty() else 100_000
        return print_table(
            items,
            Console(emoji=False, markup=False, file=out, width=width, soft_wrap=False),
            columns=columns,
            warn=warn,
        )
    raise ValueError(f"unknown format: {fmt}")


__all__ = ["ITEM_FORMATS", "Columns", "write_csv", "write_ids", "write_items", "write_json_array", "write_ndjson"]

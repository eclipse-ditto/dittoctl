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
"""The shape of things: which paths occur in a set of things, with their JSON types and example values.

Ditto things are schemaless, so knowing the paths and types is what it takes to write RQL filters and
field selectors; this works for things without a WoT model, too.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from dittoctl.formats.flatten import flatten

MAX_EXAMPLE_LENGTH = 120
MAX_EXAMPLE_ITEMS = 3


def json_type(value: Any) -> str:
    """The JSON type of a value; numbers are 'integer' or 'number', arrays carry their item types."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        items = sorted({json_type(item) for item in value})
        return f"array<{'|'.join(items)}>" if items else "array"
    return "object"


def _example(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_EXAMPLE_LENGTH:
        return value[: MAX_EXAMPLE_LENGTH - 1] + "…"
    if isinstance(value, list):
        return [_example(item) for item in value[:MAX_EXAMPLE_ITEMS]] + (
            ["…"] if len(value) > MAX_EXAMPLE_ITEMS else []
        )
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return value if len(text) <= MAX_EXAMPLE_LENGTH else text[: MAX_EXAMPLE_LENGTH - 1] + "…"
    return value


@dataclass
class FieldStats:
    path: str
    count: int = 0
    types: set[str] = field(default_factory=set)
    examples: list[Any] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)

    def add(self, value: Any, max_examples: int) -> None:
        self.count += 1
        self.types.add(json_type(value))
        if len(self.examples) < max_examples:
            key = json.dumps(value, sort_keys=True, ensure_ascii=False)
            if key not in self._seen:
                self._seen.add(key)
                self.examples.append(_example(value))

    def to_json(self, total: int) -> dict[str, Any]:
        return {
            "path": self.path,
            "types": sorted(self.types),
            "count": self.count,
            "share": round(self.count / total, 3) if total else 0,
            "examples": self.examples,
        }


def field_stats(things: Iterable[dict[str, Any]], max_examples: int = 3) -> tuple[list[FieldStats], int]:
    """The leaf paths of the things (arrays and empty objects count as leaves), sorted by path, and the number of
    things inspected."""
    stats: dict[str, FieldStats] = {}
    total = 0
    for thing in things:
        total += 1
        for path, value in flatten(thing).items():
            stats.setdefault(path, FieldStats(path)).add(value, max_examples)
    return sorted(stats.values(), key=lambda s: s.path), total

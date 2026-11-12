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
"""Turn nested JSON into flat ``/``-separated paths for tabular output."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

SEPARATOR = "/"


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """``{"a": {"b": 1}, "c": [1, 2]}`` becomes ``{"a/b": 1, "c": [1, 2]}``; arrays stay whole."""
    if not isinstance(value, dict):
        return {prefix or "value": value}
    if not value and prefix:
        return {prefix: {}}
    result: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}{SEPARATOR}{key}" if prefix else str(key)
        if isinstance(child, dict) and child:
            result.update(flatten(child, path))
        else:
            result[path] = child
    return result


def get_path(value: Any, path: str) -> Any:
    """The value at a ``/``-separated path, or ``None`` if any segment is missing."""
    current = value
    for segment in path.strip(SEPARATOR).split(SEPARATOR):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def cell(value: Any) -> str:
    """Render a JSON value for a table or CSV cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return json.dumps(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def short_headers(paths: Iterable[str]) -> dict[str, str]:
    """Map each path to its shortest unambiguous suffix.

    ``features/temp/properties/value`` becomes ``value`` if no other column ends in ``value``, or
    ``temp/properties/value`` if another column ends in ``properties/value``.
    """
    paths = list(paths)
    split = {p: p.split(SEPARATOR) for p in paths}
    result: dict[str, str] = {}
    for path, segments in split.items():
        for length in range(1, len(segments) + 1):
            suffix = segments[-length:]
            clashes = any(
                other != path and others[-length:] == suffix and len(others) >= length
                for other, others in split.items()
            )
            if not clashes:
                result[path] = SEPARATOR.join(suffix)
                break
        else:
            result[path] = path
    return result

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
"""JSON helpers for writes: building merge patches (RFC 7396), comparing values, editing arrays."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

# returned by merge_patch_diff when both documents are equal
NO_CHANGE: Any = object()

Equality = Callable[[Any, Any], bool]


def segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


def nested(path: str, value: Any) -> Any:
    """``nested("attributes/location/room", "lab")`` is ``{"attributes": {"location": {"room": "lab"}}}``."""
    for segment in reversed(segments(path)):
        value = {segment: value}
    return value


def contains_array(value: Any) -> bool:
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return any(contains_array(v) for v in value.values())
    return False


def deep_equal(a: Any, b: Any) -> bool:
    """Structural JSON equality: object key order doesn't matter, 1 equals 1.0, but true doesn't equal 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep_equal(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and a == b


def json_equal(a: Any, b: Any) -> bool:
    """Equality of the canonical serialization: like deep_equal, but 1 and 1.0 differ."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def equality(mode: str) -> Equality:
    return json_equal if mode == "json" else deep_equal


def array_add(current: Sequence[Any] | None, items: Sequence[Any], *, as_set: bool, equal: Equality) -> list[Any]:
    """Append items; with ``as_set`` only those not present yet (and each only once)."""
    result = list(current or [])
    for item in items:
        if as_set and any(equal(item, existing) for existing in result):
            continue
        result.append(item)
    return result


def array_remove(current: Sequence[Any] | None, items: Sequence[Any], *, equal: Equality) -> list[Any]:
    """Remove every occurrence of each item."""
    return [existing for existing in current or [] if not any(equal(existing, item) for item in items)]


def json_diff(old: Any, new: Any, path: str = "") -> list[dict[str, Any]]:
    """The differences between two JSON values as ``{"op", "path", "old", "new"}``, ops add/remove/replace.

    Objects are compared key by key, everything else (including arrays) as a whole. ``path`` is a JSON pointer.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(old.keys() | new.keys()):
            child = f"{path}/{key}"
            if key not in new:
                changes.append({"op": "remove", "path": child, "old": old[key]})
            elif key not in old:
                changes.append({"op": "add", "path": child, "new": new[key]})
            else:
                changes.extend(json_diff(old[key], new[key], child))
        return changes
    return [] if deep_equal(old, new) else [{"op": "replace", "path": path or "/", "old": old, "new": new}]


def merge_patch_diff(old: Any, new: Any) -> Any:
    """The merge patch (RFC 7396) that turns ``old`` into ``new``, or :data:`NO_CHANGE`."""
    if isinstance(old, dict) and isinstance(new, dict):
        patch: dict[str, Any] = {}
        for key in old.keys() - new.keys():
            patch[key] = None
        for key, value in new.items():
            if key not in old:
                patch[key] = value
                continue
            child = merge_patch_diff(old[key], value)
            if child is not NO_CHANGE:
                patch[key] = child
        return patch or NO_CHANGE
    return NO_CHANGE if deep_equal(old, new) else new

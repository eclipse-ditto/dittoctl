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
import pytest

from dittoctl.core.jsonops import (
    NO_CHANGE,
    array_add,
    array_remove,
    contains_array,
    deep_equal,
    json_equal,
    merge_patch_diff,
    nested,
)


def test_nested():
    assert nested("/attributes/location/room/", "lab") == {"attributes": {"location": {"room": "lab"}}}
    assert nested("", {"a": 1}) == {"a": 1}


def test_contains_array():
    assert contains_array([1])
    assert contains_array({"a": {"b": [1]}})
    assert not contains_array({"a": {"b": 1}})


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1, 1.0, True),
        (True, 1, False),
        (False, 0, False),
        ({"a": 1, "b": [1, {"c": 2}]}, {"b": [1, {"c": 2}], "a": 1}, True),
        ([1, 2], [2, 1], False),
        ("1", 1, False),
        (None, None, True),
        ({"a": None}, {}, False),
    ],
)
def test_deep_equal(a, b, expected):
    assert deep_equal(a, b) is expected


def test_json_equal_distinguishes_int_and_float():
    assert json_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert not json_equal(1, 1.0)


def test_array_add():
    assert array_add(["a"], ["a", "b"], as_set=False, equal=deep_equal) == ["a", "a", "b"]
    assert array_add(["a"], ["a", "b", "b"], as_set=True, equal=deep_equal) == ["a", "b"]
    assert array_add(None, [{"x": 1}], as_set=True, equal=deep_equal) == [{"x": 1}]


def test_array_remove():
    assert array_remove(["a", "b", "a", 1.0], ["a", 1], equal=deep_equal) == ["b"]
    assert array_remove(["a", 1.0], [1], equal=json_equal) == ["a", 1.0]
    assert array_remove(None, ["a"], equal=deep_equal) == []


def test_merge_patch_diff():
    old = {"a": 1, "b": {"c": 2, "d": 3}, "e": [1], "gone": True}
    new = {"a": 1, "b": {"c": 2, "d": 4}, "e": [1, 2], "added": {"x": 1}}
    assert merge_patch_diff(old, new) == {"b": {"d": 4}, "e": [1, 2], "added": {"x": 1}, "gone": None}
    assert merge_patch_diff(old, dict(old)) is NO_CHANGE
    assert merge_patch_diff(1, 1.0) is NO_CHANGE
    assert merge_patch_diff({"a": 1}, "text") == "text"

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
import json

import pytest

from dittoctl.core.conditions import Conditions, IfEqual, LiveTimeoutStrategy, normalize_etag


@pytest.mark.parametrize(
    ("value", "expected"),
    [("rev:5", '"rev:5"'), ('"rev:5"', '"rev:5"'), ("*", "*"), ('W/"rev:5"', '"rev:5"'), (" rev:1 ", '"rev:1"')],
)
def test_normalize_etag(value, expected):
    assert normalize_etag(value) == expected


def test_empty_conditions_produce_nothing():
    conditions = Conditions()
    assert conditions.headers() == {}
    assert conditions.params() == {}
    assert conditions.is_empty()


def test_all_conditions_map_to_headers_and_params():
    conditions = Conditions(
        if_match="rev:3",
        if_none_match="*",
        if_equal=IfEqual.SKIP,
        condition='eq(attributes/fw,"1.2")',
        patch_conditions={"/features/temp": "exists(features/temp)"},
        live_condition="eq(attributes/online,true)",
        live_timeout_strategy=LiveTimeoutStrategy.USE_TWIN,
    )
    headers = conditions.headers()
    assert headers["If-Match"] == '"rev:3"'
    assert headers["If-None-Match"] == "*"
    assert headers["If-Equal"] == "skip"
    assert json.loads(headers["merge-thing-patch-conditions"]) == {"/features/temp": "exists(features/temp)"}
    assert headers["live-channel-timeout-strategy"] == "use-twin"
    assert conditions.params() == {
        "condition": 'eq(attributes/fw,"1.2")',
        "live-channel-condition": "eq(attributes/online,true)",
    }
    assert not conditions.is_empty()


def test_replace_returns_modified_copy():
    original = Conditions(if_equal=IfEqual.SKIP)
    changed = original.replace(if_match="rev:1")
    assert original.if_match is None
    assert changed.if_match == "rev:1"
    assert changed.if_equal is IfEqual.SKIP

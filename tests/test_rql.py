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

from dittoctl.core import rql


@pytest.mark.parametrize(
    "expression",
    [
        'eq(attributes/location,"kitchen")',
        "ne(attributes/count,-1.5e3)",
        "gt(_modified,'2026-11-01T00:00:00Z')",
        'like(attributes/name,"sensor-*")',
        'ilike(attributes/name,"SENSOR-?")',
        'in(attributes/type,"a","b",3,true,null)',
        "exists(features/temp/properties/value)",
        "empty(attributes/tags)",
        "not(exists(attributes/x))",
        'and(eq(a,1),or(eq(b,false),not(eq(c,"x"))))',
        'eq(features/*/properties/status,"on")',
        'eq(attributes/quote,"say \\"hi\\"")',
    ],
)
def test_valid_expressions_roundtrip(expression):
    assert rql.normalize(expression) == expression


def test_whitespace_is_accepted_and_removed():
    text = """
        and(
            eq(attributes/a, "x y"),
            in(attributes/n, 1, 2)
        )
    """
    assert rql.normalize(text) == 'and(eq(attributes/a,"x y"),in(attributes/n,1,2))'


def test_parsed_values():
    node = rql.parse('in(p,"s\\"q",1.5,-2,true,false,null)')
    assert isinstance(node, rql.Comparison)
    assert [v.value for v in node.values] == ['s"q', 1.5, -2, True, False, None]


def test_pretty_format():
    node = rql.parse("and(eq(a,1),or(exists(b),not(eq(c,2))))")
    assert rql.pretty(node) == "\n".join(
        [
            "and(",
            "  eq(a,1),",
            "  or(",
            "    exists(b),",
            "    not(",
            "      eq(c,2)",
            "    )",
            "  )",
            ")",
        ]
    )


@pytest.mark.parametrize(
    ("expression", "message", "position"),
    [
        ("", "empty", 0),
        ("eq(attributes/x,unquoted)", "expected a value", 16),
        ("eq(attributes/x,1abc)", "expected a value", 16),
        ("foo(a,1)", "unknown operator 'foo'", 0),
        ("EQ(a,1)", "operators are lowercase: 'eq'", 0),
        ("eq(a,1", "expected ')'", 6),
        ("eq(a,1,2)", "it takes one value", 6),
        ("exists(a,1)", "it takes only a property", 8),
        ("eq(a,1))", "unexpected input after the end", 7),
        ('eq(a,"open)', "unterminated string", 5),
        ("and(eq(a,1) eq(b,2))", "expected ')'", 12),
        ("eq(,1)", "expected a property path", 3),
        ("not(eq(a,1),eq(b,2))", "to close 'not('", 11),
    ],
)
def test_errors_report_position(expression, message, position):
    with pytest.raises(rql.RqlError) as info:
        rql.parse(expression)
    assert message in info.value.message
    assert info.value.position == position


def test_render_points_at_the_error():
    with pytest.raises(rql.RqlError) as info:
        rql.parse("and(eq(attributes/a,x),exists(b))")
    lines = info.value.render().splitlines()
    assert lines[1] == "  and(eq(attributes/a,x),exists(b))"
    assert lines[2] == "  " + " " * 20 + "^"


def test_render_shortens_long_expressions():
    expression = "and(" + ",".join(f"eq(attributes/a{i},{i})" for i in range(30)) + ",eq(x,bad))"
    with pytest.raises(rql.RqlError) as info:
        rql.parse(expression)
    snippet, caret = info.value.render(width=40).splitlines()[1:]
    assert snippet.startswith("  …")
    assert snippet[caret.index("^") :].startswith("bad")

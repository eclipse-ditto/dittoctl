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
"""Offline parser and formatter for Ditto RQL filter expressions.

Grammar (see https://eclipse.dev/ditto/basic-rql.html)::

    query      = comparison | in | property-op | logical | not
    comparison = ("eq" | "ne" | "gt" | "ge" | "lt" | "le" | "like" | "ilike") "(" property "," value ")"
    in         = "in" "(" property "," value ("," value)* ")"
    property-op= ("exists" | "empty") "(" property ")"
    logical    = ("and" | "or") "(" query ("," query)* ")"
    not        = "not" "(" query ")"
    value      = string | number | "true" | "false" | "null"

Whitespace between tokens is accepted here; :func:`compact` produces the canonical form without it,
which is what dittoctl sends to Ditto.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

COMPARISON_OPS = ("eq", "ne", "gt", "ge", "lt", "le", "like", "ilike")
PROPERTY_OPS = ("exists", "empty")
LOGICAL_OPS = ("and", "or")
ALL_OPS = (*COMPARISON_OPS, "in", *PROPERTY_OPS, *LOGICAL_OPS, "not")

_NUMBER = re.compile(r"-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?")
_OPERATOR = re.compile(r"[A-Za-z]+")
_PROPERTY_END = set(",()\"' \t\r\n")


class RqlError(ValueError):
    def __init__(self, message: str, source: str, position: int) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.position = position

    def render(self, width: int = 60) -> str:
        """The message plus the relevant part of the expression with a caret under the error position."""
        start = max(0, self.position - width // 2)
        end = min(len(self.source), start + width)
        snippet = self.source[start:end].replace("\n", " ").replace("\t", " ")
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(self.source) else ""
        caret = " " * (len(prefix) + self.position - start) + "^"
        return f"{self.message} (at position {self.position})\n  {prefix}{snippet}{suffix}\n  {caret}"

    def __str__(self) -> str:
        return f"{self.message} (at position {self.position})"


@dataclass(frozen=True)
class Value:
    raw: str  # exactly as written, so that strings keep their quotes and escapes
    value: Any


@dataclass(frozen=True)
class Comparison:
    op: str
    property: str
    values: tuple[Value, ...]


@dataclass(frozen=True)
class PropertyOp:
    op: str
    property: str


@dataclass(frozen=True)
class Logical:
    op: str
    children: tuple[Node, ...]


Node = Comparison | PropertyOp | Logical


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def error(self, message: str, position: int | None = None) -> RqlError:
        return RqlError(message, self.text, self.pos if position is None else position)

    def skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def peek(self) -> str:
        self.skip_ws()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, char: str, context: str) -> None:
        found = self.peek()
        if found != char:
            what = f"'{found}'" if found else "the end of the expression"
            raise self.error(f"expected '{char}' {context}, found {what}")
        self.pos += 1

    def parse(self) -> Node:
        if not self.text.strip():
            raise self.error("the expression is empty", 0)
        node = self.query()
        if self.peek():
            raise self.error("unexpected input after the end of the expression")
        return node

    def query(self) -> Node:
        self.skip_ws()
        start = self.pos
        match = _OPERATOR.match(self.text, self.pos)
        if not match:
            raise self.error("expected an operator such as eq, in, exists, and, or, not")
        op = match.group(0)
        if op not in ALL_OPS:
            hint = f"; operators are lowercase: '{op.lower()}'" if op.lower() in ALL_OPS else ""
            raise self.error(f"unknown operator '{op}'{hint}", start)
        self.pos = match.end()
        self.expect("(", f"after '{op}'")
        if op in LOGICAL_OPS or op == "not":
            children = [self.query()]
            while op != "not" and self.peek() == ",":
                self.pos += 1
                children.append(self.query())
            self.expect(")", f"to close '{op}('" + ("" if op == "not" else " or ',' before the next query"))
            return Logical(op, tuple(children))
        prop = self.property()
        if op in PROPERTY_OPS:
            self.expect(")", f"to close '{op}(' (it takes only a property)")
            return PropertyOp(op, prop)
        self.expect(",", f"after the property of '{op}('")
        values = [self.value()]
        while op == "in" and self.peek() == ",":
            self.pos += 1
            values.append(self.value())
        closing = "after the values of 'in('" if op == "in" else f"to close '{op}(' (it takes one value)"
        self.expect(")", closing)
        return Comparison(op, prop, tuple(values))

    def property(self) -> str:
        self.skip_ws()
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in _PROPERTY_END:
            self.pos += 1
        if self.pos == start:
            raise self.error("expected a property path such as attributes/location or _modified")
        return self.text[start : self.pos]

    def value(self) -> Value:
        self.skip_ws()
        start = self.pos
        char = self.text[self.pos] if self.pos < len(self.text) else ""
        if char in ('"', "'"):
            return self.string(char)
        if match := _NUMBER.match(self.text, self.pos):
            end = match.end()
            # "1abc" is not a number followed by garbage, it's an invalid value
            if end >= len(self.text) or self.text[end] in _PROPERTY_END:
                self.pos = end
                raw = match.group(0)
                return Value(raw, json.loads(raw))
        for keyword, value in (("true", True), ("false", False), ("null", None)):
            end = self.pos + len(keyword)
            if self.text.startswith(keyword, self.pos) and (end >= len(self.text) or self.text[end] in _PROPERTY_END):
                self.pos = end
                return Value(keyword, value)
        raise self.error(
            "expected a value: a quoted string, a number, true, false or null (strings need quotes)", start
        )

    def string(self, quote: str) -> Value:
        start = self.pos
        self.pos += 1
        chars: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == "\\" and self.pos + 1 < len(self.text):
                chars.append(self.text[self.pos + 1])
                self.pos += 2
                continue
            if char == quote:
                self.pos += 1
                return Value(self.text[start : self.pos], "".join(chars))
            chars.append(char)
            self.pos += 1
        raise self.error(f"unterminated string: the {quote} is never closed", start)


def parse(text: str) -> Node:
    """Parse an RQL filter expression. Raises :class:`RqlError` with the position of the first error."""
    return _Parser(text).parse()


def compact(node: Node) -> str:
    """The canonical single-line form, without whitespace."""
    if isinstance(node, Logical):
        return f"{node.op}({','.join(compact(c) for c in node.children)})"
    if isinstance(node, PropertyOp):
        return f"{node.op}({node.property})"
    return f"{node.op}({node.property},{','.join(v.raw for v in node.values)})"


def pretty(node: Node, indent: str = "  ", _level: int = 0) -> str:
    """Multi-line form: logical operators on their own lines, comparisons on one line."""
    if not isinstance(node, Logical):
        return indent * _level + compact(node)
    inner = ",\n".join(pretty(child, indent, _level + 1) for child in node.children)
    pad = indent * _level
    return f"{pad}{node.op}(\n{inner}\n{pad})"


# Ditto rejects exists() on these whole objects ("Unknown property name"), see eclipse-ditto/ditto#2637
_UNSUPPORTED_EXISTS = ("attributes", "features")


def warnings(node: Node) -> list[str]:
    """Problems Ditto will report although the expression is valid RQL."""
    if isinstance(node, Logical):
        return [w for child in node.children for w in warnings(child)]
    if isinstance(node, PropertyOp) and node.op == "exists" and node.property.strip("/") in _UNSUPPORTED_EXISTS:
        name = node.property.strip("/")
        return [
            f"Ditto rejects exists({name}) on the whole object (eclipse-ditto/ditto#2637); "
            f"use a concrete path such as exists({name}/<name>)"
        ]
    return []


def normalize(text: str) -> str:
    """Validate an expression and return its canonical form."""
    return compact(parse(text))

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
import csv
import io
import json
import re
import tracemalloc

import pytest

from dittoctl.formats import Columns, write_csv, write_ids, write_items, write_json_array, write_ndjson
from dittoctl.formats.flatten import cell, flatten, get_path, short_headers
from dittoctl.formats.tabular import excel_timestamp

THING = {
    "thingId": "org.example:a",
    "attributes": {"location": {"room": "lab", "floor": 2}, "tags": ["x", "y"], "empty": {}},
    "features": {"temp": {"properties": {"value": 21.5}}},
}


def test_flatten():
    assert flatten(THING) == {
        "thingId": "org.example:a",
        "attributes/location/room": "lab",
        "attributes/location/floor": 2,
        "attributes/tags": ["x", "y"],
        "attributes/empty": {},
        "features/temp/properties/value": 21.5,
    }
    assert flatten(5) == {"value": 5}


def test_get_path():
    assert get_path(THING, "attributes/location") == {"room": "lab", "floor": 2}
    assert get_path(THING, "/features/temp/properties/value") == 21.5
    assert get_path(THING, "attributes/missing/x") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (True, "true"), (False, "false"), ("s", "s"), (2, "2"), (1.5, "1.5"), (["a", 1], '["a",1]'),
     ({"ü": 1}, '{"ü":1}')],
)  # fmt: skip
def test_cell(value, expected):
    assert cell(value) == expected


def test_short_headers():
    paths = ["thingId", "features/temp/properties/value", "features/humidity/properties/value", "attributes/room"]
    assert short_headers(paths) == {
        "thingId": "thingId",
        "features/temp/properties/value": "temp/properties/value",
        "features/humidity/properties/value": "humidity/properties/value",
        "attributes/room": "room",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-06T15:19:54.123456789Z", "2026-11-06 15:19:54"),
        ("2026-11-06T17:19:54+02:00", "2026-11-06 15:19:54"),
        ("2026-11-06", "2026-11-06"),
        ("not a date", "not a date"),
    ],
)
def test_excel_timestamp(value, expected):
    assert excel_timestamp(value) == expected


def read_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_csv_discovers_columns_from_first_rows_and_warns_about_later_ones():
    warnings = []
    items = [
        {"thingId": "a", "attributes": {"x": 1}},
        {"thingId": "b", "attributes": {"y": 2}},
        {"thingId": "c", "z": 3},
    ]
    out = io.StringIO()
    count = write_csv(items, out, columns=Columns(discover_rows=2), warn=warnings.append)
    assert count == 3
    assert read_csv(out.getvalue()) == [
        ["thingId", "attributes/x", "attributes/y"],
        ["a", "1", ""],
        ["b", "", "2"],
        ["c", "", ""],
    ]
    assert len(warnings) == 1
    assert "z" in warnings[0]


def test_csv_discover_all_rows():
    items = [{"a": 1}, {"b": 2}]
    out = io.StringIO()
    write_csv(items, out, columns=Columns(discover_rows=0))
    assert read_csv(out.getvalue())[0] == ["a", "b"]


def test_csv_explicit_columns_can_name_parent_objects():
    out = io.StringIO()
    write_csv([THING], out, columns=Columns(explicit=["thingId", "attributes/location", "attributes/nope"]))
    assert read_csv(out.getvalue()) == [
        ["thingId", "attributes/location", "attributes/nope"],
        ["org.example:a", '{"room":"lab","floor":2}', ""],
    ]


def test_csv_options():
    out = io.StringIO()
    items = [{"thingId": "a", "_modified": "2026-11-06T15:19:54Z", "note": "multi\nline"}]
    write_csv(items, out, columns=Columns(short=True), delimiter=";", header=False, excel=True)
    assert out.getvalue() == 'a;2026-11-06 15:19:54;"multi\nline"\n'


def test_csv_memory_stays_flat_for_large_streams():
    def things(n):
        for i in range(n):
            yield {"thingId": f"org.example:t{i}", "attributes": {"i": i, "name": f"thing {i}"}}

    class Sink(io.TextIOBase):
        def write(self, s):
            return len(s)

    tracemalloc.start()
    write_csv(things(1_000), Sink())
    _, small = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    write_csv(things(100_000), Sink())
    _, large = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # only the discovery window is buffered: 100x the rows must not need noticeably more memory
    assert large < small * 2 + 100_000


def test_json_array_streaming():
    out = io.StringIO()
    assert write_json_array(iter([{"a": 1}, {"b": [1, 2]}]), out) == 2
    assert json.loads(out.getvalue()) == [{"a": 1}, {"b": [1, 2]}]
    empty = io.StringIO()
    write_json_array(iter([]), empty)
    assert json.loads(empty.getvalue()) == []


def test_ndjson_and_ids():
    out = io.StringIO()
    write_ndjson([{"thingId": "a", "ü": 1}, {"thingId": "b"}], out)
    assert out.getvalue() == '{"thingId":"a","ü":1}\n{"thingId":"b"}\n'
    ids = io.StringIO()
    assert write_ids([{"thingId": "a"}, {"other": 1}, {"thingId": "b"}], ids) == 2
    assert ids.getvalue() == "a\nb\n"


def test_table_to_non_terminal_does_not_wrap():
    out = io.StringIO()
    long_id = "org.example:" + "x" * 150
    write_items([{"thingId": long_id, "attributes": {"n": 1}}], "table", out)
    lines = out.getvalue().splitlines()
    assert lines[0].split() == ["thingId", "attributes/n"]
    assert long_id in lines[1]


def test_table_shows_values_literally():
    out = io.StringIO()
    write_items([{"thingId": "ns:a:", "note": "[red]alert[/red] :smile:"}], "table", out)
    row = out.getvalue().splitlines()[1]
    assert "ns:a:" in row
    assert "[red]alert[/red] :smile:" in row


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize("write", [write_ndjson, write_json_array])
def test_json_is_highlighted_on_a_terminal_only(write, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    items = [{"thingId": "ns:a:", "note": "[bold]x[/bold]", "on": True}]
    plain = io.StringIO()
    write(items, plain)
    terminal = Terminal()
    write(items, terminal)
    assert "\x1b[" not in plain.getvalue()
    assert "\x1b[" in terminal.getvalue()
    # only colors are added: no markup, no emoji, the same JSON text
    assert re.sub(r"\x1b\[[0-9;]*m", "", terminal.getvalue()) == plain.getvalue()

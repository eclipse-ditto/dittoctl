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
from __future__ import annotations

import json

import httpx
import pytest
import respx

from dittoctl.core.wot import compact_td, compact_thing_description, feature_links

URL = "http://ditto.test"
MODELS = "https://models.example.org"
ERROR_RESPONSE = [{"success": False, "schema": "dittoError"}]


def form(op: str, href: str, method: str = "GET") -> dict:
    return {
        "op": op,
        "href": href,
        "htv:methodName": method,
        "contentType": "application/json",
        "additionalResponses": ERROR_RESPONSE,
    }


def thing_td(*features: str) -> dict:
    return {
        "@context": ["https://www.w3.org/2022/wot/td/v1.1", {"om2": "http://example.org/om-2/"}],
        "@type": "Thing",
        "id": "urn:org.example:lamp-1",
        "base": f"{URL}/api/2/things/org.example:lamp-1/",
        "title": "Floor lamp",
        "security": "basic_sc",
        "securityDefinitions": {"basic_sc": {"in": "header", "scheme": "basic"}},
        "schemaDefinitions": {"dittoError": {"type": "object"}},
        "forms": [form("readallproperties", "attributes")],
        "links": [
            {"rel": "type", "href": f"{MODELS}/floor-lamp-1.0.0.tm.jsonld", "type": "application/tm+json"},
            *({"rel": "item", "href": f"features/{f}", "type": "application/td+json"} for f in features),
        ],
        "properties": {
            "serialNo": {
                "title": "Serial number",
                "type": "string",
                "readOnly": True,
                "forms": [form("readproperty", "attributes/serialNo")],
            }
        },
        "actions": {
            "switch-all": {
                "title": "Switch all spots",
                "input": {"type": "boolean"},
                "forms": [form("invokeaction", "inbox/messages/switch-all", "POST")],
            }
        },
    }


def spot_td(name: str) -> dict:
    return {
        "@context": ["https://www.w3.org/2022/wot/td/v1.1", {"time": "http://example.org/time#"}],
        "@type": "Thing",
        "base": f"{URL}/api/2/things/org.example:lamp-1/features/{name}/",
        "title": "Spot",
        "links": [
            {"rel": "collection", "href": "../../"},
            {"rel": "type", "href": f"{MODELS}/spot-1.0.0.tm.jsonld"},
        ],
        "properties": {
            "dimmer-level": {
                "@type": "om2:Percentage",
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "forms": [
                    form("readproperty", "properties/dimmer-level"),
                    form("writeproperty", "properties/dimmer-level", "PUT"),
                ],
            }
        },
        "events": {"overheated": {"data": {"type": "number"}, "forms": [form("subscribeevent", "outbox/messages/x")]}},
    }


def test_feature_links():
    assert feature_links(thing_td("Spot1", "Spot2")) == ["Spot1", "Spot2"]
    assert feature_links({"links": [{"rel": "collection", "href": "features/x"}]}) == []


def test_compact_td_keeps_only_what_describes_the_thing():
    assert compact_td(thing_td("Spot1")) == {
        "title": "Floor lamp",
        "model": f"{MODELS}/floor-lamp-1.0.0.tm.jsonld",
        "properties": {
            "serialNo": {"path": "attributes/serialNo", "title": "Serial number", "type": "string", "readOnly": True}
        },
        "actions": {
            "switch-all": {
                "path": "inbox/messages/switch-all",
                "title": "Switch all spots",
                "input": {"type": "boolean"},
            }
        },
    }


def test_compact_td_keeps_semantic_types_and_own_schemas():
    td = {
        **spot_td("Spot1"),
        "@type": ["Thing", "saref:LightSwitch"],
        "schemaDefinitions": {"dittoError": {}, "rgb": {}},
    }
    compact = compact_td(td)
    assert compact["@type"] == ["Thing", "saref:LightSwitch"]
    assert compact["schemaDefinitions"] == {"rgb": {}}
    assert compact["properties"]["dimmer-level"]["@type"] == "om2:Percentage"


def test_compact_thing_description_merges_prefixes_and_identical_features():
    td = {
        **thing_td("Spot1", "Spot2", "Broken"),
        "features": {
            "Spot1": spot_td("Spot1"),
            "Spot2": spot_td("Spot2"),
            "Broken": {"error": "wot:thingmodel.notfound", "message": "not found"},
        },
    }
    compact = compact_thing_description(td)
    assert compact["prefixes"] == {"om2": "http://example.org/om-2/", "time": "http://example.org/time#"}
    assert compact["features"]["Spot1"]["properties"]["dimmer-level"]["path"] == "properties/dimmer-level"
    assert compact["features"]["Spot2"] == {"sameAs": "Spot1"}
    assert compact["features"]["Broken"] == {"error": "wot:thingmodel.notfound", "message": "not found"}


@pytest.fixture
def ditto():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


def test_td_with_features(run, ditto):
    thing = ditto.get("/api/2/things/org.example:lamp-1").mock(
        return_value=httpx.Response(200, json=thing_td("Spot1", "Broken"))
    )
    ditto.get("/api/2/things/org.example:lamp-1/features/Spot1").mock(
        return_value=httpx.Response(200, json=spot_td("Spot1"))
    )
    ditto.get("/api/2/things/org.example:lamp-1/features/Broken").mock(
        return_value=httpx.Response(
            404, json={"status": 404, "error": "wot:thingmodel.notfound", "message": "The model was not found."}
        )
    )
    result = run("--url", URL, "things", "td", "org.example:lamp-1", "--with-features")
    assert result.exit_code == 0, result.stderr
    full = json.loads(result.stdout)
    assert full["securityDefinitions"]
    assert full["features"]["Spot1"]["base"].endswith("/features/Spot1/")
    assert full["features"]["Broken"] == {"error": "wot:thingmodel.notfound", "message": "The model was not found."}
    assert thing.calls.last.request.headers["Accept"] == "application/td+json"

    result = run("--url", URL, "things", "td", "org.example:lamp-1", "--with-features", "--compact")
    assert result.stdout.count("\n") == 1
    compact = json.loads(result.stdout)
    assert "forms" not in result.stdout
    assert compact["features"]["Spot1"]["events"] == {
        "overheated": {"path": "outbox/messages/x", "data": {"type": "number"}}
    }


def test_td_feature_and_with_features_exclude_each_other(run):
    result = run("--url", URL, "things", "td", "org.example:lamp-1", "--feature", "Spot1", "--with-features")
    assert result.exit_code == 1
    assert "either --feature or --with-features" in result.stderr


def test_compact_refers_to_repeated_schemas():
    transitions = {
        "title": "Transitions",
        "description": "Start of each transition and the temperature to apply from then on.",
        "type": "array",
        "items": {"type": "object", "properties": {"minutes": {"type": "integer"}, "celsius": {"type": "number"}}},
    }
    days = {day: {"title": day, "type": "object", "properties": {"transitions": transitions}} for day in ("MON", "TUE")}
    td = {
        "title": "Schedule",
        "properties": {"days": {"type": "object", "properties": days, "forms": [form("x", "p")]}},
    }
    compact = compact_thing_description(td)
    days_out = compact["properties"]["days"]["properties"]
    assert days_out["MON"]["properties"]["transitions"] == transitions
    assert days_out["TUE"]["properties"]["transitions"] == {
        "$ref": "#/properties/days/properties/MON/properties/transitions"
    }

    short = compact_thing_description(td, schema_descriptions=False)
    assert "description" not in short["properties"]["days"]["properties"]["MON"]["properties"]["transitions"]

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
"""WoT Thing Descriptions: a thing together with its features, and a compact projection.

The Thing Descriptions Ditto generates are verbose: every property carries four forms (read, write,
merge, observe) that each repeat the content type and Ditto's error schema. Their paths and methods
follow fixed Ditto conventions, so the compact projection keeps only what describes the thing itself:
titles, descriptions, data schemas, units and semantic types, plus the Ditto path of each affordance.
"""

from __future__ import annotations

import json
from typing import Any

from dittoctl.core.client import DittoClient
from dittoctl.core.things import thing_description
from dittoctl.errors import DittoError

AFFORDANCES = ("properties", "actions", "events")
FEATURES_PREFIX = "features/"
# added by Ditto to every TD, referenced only by the forms' additionalResponses
DITTO_ERROR_SCHEMA = "dittoError"
# repeated data schemas at least this long (as compact JSON) are replaced by a reference to the first one
MIN_SHARED_SCHEMA = 200


def feature_links(td: dict[str, Any]) -> list[str]:
    """The names of the features a thing's TD links to (``rel: item``), in order."""
    names = []
    for link in td.get("links") or []:
        href = link.get("href", "")
        if link.get("rel") == "item" and href.startswith(FEATURES_PREFIX):
            names.append(href.removeprefix(FEATURES_PREFIX))
    return names


def thing_description_with_features(client: DittoClient, thing_id: str) -> dict[str, Any]:
    """The thing's TD with the TDs of all its features under ``features``.

    A feature whose TD can't be retrieved (for example because its model can't be resolved) gets
    ``{"error": ...}`` instead, so the rest of the thing is still described.
    """
    td = thing_description(client, thing_id)
    features: dict[str, Any] = {}
    for name in feature_links(td):
        try:
            features[name] = thing_description(client, thing_id, name)
        except DittoError as exc:
            features[name] = {"error": exc.error or str(exc.status), "message": exc.message}
    if features:
        td = {**td, "features": features}
    return td


def _first_href(forms: list[dict[str, Any]] | None) -> str | None:
    return next((form["href"] for form in forms or [] if "href" in form), None)


def _compact_affordance(affordance: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    path = _first_href(affordance.get("forms"))
    if path:
        result["path"] = path
    result.update((k, v) for k, v in affordance.items() if k not in ("forms", "additionalResponses"))
    return result


def _prefixes(td: dict[str, Any]) -> dict[str, str]:
    context = td.get("@context")
    entries = context if isinstance(context, list) else [context]
    prefixes: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict):
            prefixes.update((k, v) for k, v in entry.items() if isinstance(v, str))
    return prefixes


def compact_td(td: dict[str, Any]) -> dict[str, Any]:
    """The parts of a TD that describe the thing, without forms, security and Ditto boilerplate.

    Each affordance gets the ``path`` of its first form, relative to the TD's base: the thing for a
    thing's TD, ``features/<name>`` for a feature's TD.
    """
    if "error" in td and "title" not in td:
        return td
    result: dict[str, Any] = {}
    for key in ("title", "description"):
        if key in td:
            result[key] = td[key]
    if td.get("@type") not in (None, "Thing"):
        result["@type"] = td["@type"]
    model = next((link["href"] for link in td.get("links") or [] if link.get("rel") == "type"), None)
    if model:
        result["model"] = model
    for kind in AFFORDANCES:
        affordances = td.get(kind)
        if affordances:
            result[kind] = {name: _compact_affordance(a) for name, a in affordances.items()}
    schemas = {k: v for k, v in (td.get("schemaDefinitions") or {}).items() if k != DITTO_ERROR_SCHEMA}
    if schemas:
        result["schemaDefinitions"] = schemas
    return result


def compact_thing_description(td: dict[str, Any], *, schema_descriptions: bool = True) -> dict[str, Any]:
    """:func:`compact_td` for a TD from :func:`thing_description_with_features`, or for a single TD.

    The ``@context`` prefixes of all TDs (e.g. ``om2`` for units) are merged into one ``prefixes``
    map. A feature described exactly like an earlier one becomes ``{"sameAs": "<earlier feature>"}``, and
    a data schema repeated within the properties, actions and events (e.g. the same schema for each day of
    the week) becomes a JSON Schema reference to its first occurrence, ``{"$ref": "#/features/..."}``. Without
    ``schema_descriptions``, the descriptions inside data schemas are left out; those of the properties,
    actions and events themselves stay.
    """
    prefixes = _prefixes(td)
    result = compact_td(td)
    features: dict[str, Any] = {}
    seen: list[tuple[dict[str, Any], str]] = []
    for name, feature_td in (td.get("features") or {}).items():
        prefixes.update(_prefixes(feature_td))
        compact = compact_td(feature_td)
        same = next((earlier for described, earlier in seen if described == compact), None)
        if same is not None:
            features[name] = {"sameAs": same}
            continue
        features[name] = compact
        if "error" not in compact:
            seen.append((compact, name))
    if features:
        result["features"] = features
    result = _share_schemas(result, "", {}, inside=False, descriptions=schema_descriptions)
    return {"prefixes": prefixes, **result} if prefixes else result


def _pointer(path: str, key: str) -> str:
    return f"{path}/{key.replace('~', '~0').replace('/', '~1')}"


def _share_schemas(node: Any, path: str, seen: dict[str, str], *, inside: bool, descriptions: bool) -> Any:
    """Replace repeated data schemas below the affordances (objects with a ``path``) by references."""
    if isinstance(node, list):
        return [
            _share_schemas(v, f"{path}/{i}", seen, inside=inside, descriptions=descriptions) for i, v in enumerate(node)
        ]
    if not isinstance(node, dict):
        return node
    # only data schemas (with a type), not maps of property names, so that a reference is unambiguous
    if inside and "type" in node:
        key = json.dumps(node, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(key) >= MIN_SHARED_SCHEMA:
            if key in seen:
                return {"$ref": "#" + seen[key]}
            seen[key] = path
    affordance = "path" in node and not inside
    return {
        k: _share_schemas(v, _pointer(path, k), seen, inside=inside or affordance, descriptions=descriptions)
        for k, v in node.items()
        if descriptions or not inside or k != "description"
    }

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
"""Per-thing write operations for the bulk engine. Each returns an :class:`Outcome` or raises; the engine
classifies errors. With ``dry_run`` nothing is written and the outcome describes the planned request."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dittoctl.core.bulk import Category, Outcome, is_unchanged
from dittoctl.core.client import DittoClient
from dittoctl.core.conditions import Conditions
from dittoctl.core.jsonops import Equality, array_add, array_remove, deep_equal, segments
from dittoctl.core.things import thing_path
from dittoctl.errors import DittoctlError, DittoError

Operation = Callable[[str], Outcome]


def _planned(thing_id: str, method: str, path: str, body: Any = None, conditions: Conditions | None = None) -> Outcome:
    plan: dict[str, Any] = {"method": method, "path": path}
    if body is not None:
        plan["body"] = body
    if conditions and not conditions.is_empty():
        plan["headers"] = conditions.headers()
        if params := conditions.params():
            plan["params"] = params
    return Outcome(thing_id, Category.PLANNED, detail=plan)


def merge_operation(
    client: DittoClient, path: str, body: Any, conditions: Conditions, *, dry_run: bool = False
) -> Operation:
    """PATCH (merge) ``body`` at ``path`` of each thing; things that don't exist are reported as not found.

    Ditto creates a thing that doesn't exist when merging at its root, so a mistyped id would silently
    create a new thing. Root merges therefore send ``If-Match: *`` (only if the thing exists), unless the
    caller set ``If-Match`` or ``If-None-Match`` itself. Merges below the root fail with 404 anyway.
    """
    require_existing = not segments(path) and not conditions.if_match and not conditions.if_none_match
    if require_existing:
        conditions = conditions.replace(if_match="*")

    def operation(thing_id: str) -> Outcome:
        target = thing_path(thing_id, path)
        if dry_run:
            return _planned(thing_id, "PATCH", target, body, conditions)
        try:
            response = client.patch(target, json=body, conditions=conditions)
        except DittoError as e:
            # with If-Match: *, a failed precondition that isn't If-Equal's "unchanged" means the thing is missing
            if require_existing and e.status == 412 and not e.condition_failed and not is_unchanged(e):
                return Outcome(thing_id, Category.NOT_FOUND, 404, "things:thing.notfound", "the thing doesn't exist")
            raise
        return Outcome(thing_id, Category.OK, response.status)

    return operation


def delete_operation(client: DittoClient, conditions: Conditions, *, dry_run: bool = False) -> Operation:
    def operation(thing_id: str) -> Outcome:
        target = thing_path(thing_id)
        if dry_run:
            return _planned(thing_id, "DELETE", target, conditions=conditions)
        response = client.delete(target, conditions=conditions)
        return Outcome(thing_id, Category.OK, response.status)

    return operation


def put_operation(
    client: DittoClient,
    things: Mapping[str, Any],
    conditions: Conditions,
    *,
    dry_run: bool = False,
) -> Operation:
    """PUT the given JSON of each thing. With ``If-None-Match: *`` existing things count as 'exists'."""
    create_only = conditions.if_none_match == "*"

    def operation(thing_id: str) -> Outcome:
        target = thing_path(thing_id)
        if dry_run:
            return _planned(thing_id, "PUT", target, things[thing_id], conditions)
        try:
            response = client.put(target, json=things[thing_id], conditions=conditions)
        except DittoError as e:
            if create_only and e.status == 412 and not e.condition_failed:
                return Outcome(thing_id, Category.EXISTS, 412, e.error, "the thing already exists")
            raise
        return Outcome(thing_id, Category.OK, response.status)

    return operation


def array_operation(
    client: DittoClient,
    path: str,
    items: Sequence[Any],
    *,
    remove: bool = False,
    as_set: bool = False,
    equal: Equality = deep_equal,
    conflict_retries: int = 3,
    dry_run: bool = False,
) -> Operation:
    """Add items to, or remove them from, the array at ``path`` of each thing.

    Read-modify-write with optimistic concurrency: the array is read together with its ETag and written with
    ``If-Match`` (``If-None-Match: *`` if it doesn't exist yet). If another writer changed it in between, it is
    read again, up to ``conflict_retries`` times. Things whose array wouldn't change are not written at all.
    """

    def operation(thing_id: str) -> Outcome:
        target = thing_path(thing_id, path)
        for _ in range(conflict_retries + 1):
            try:
                response = client.get(target)
                current, etag = response.body, response.etag
            except DittoError as e:
                if e.status != 404:
                    raise
                current, etag = None, None
            if current is not None and not isinstance(current, list):
                raise DittoctlError(f"{path} is not an array but {type(current).__name__}")
            updated = (
                array_remove(current, items, equal=equal)
                if remove
                else array_add(current, items, as_set=as_set, equal=equal)
            )
            if current is not None and deep_equal(current, updated):
                return Outcome(thing_id, Category.UNCHANGED, message="nothing to change")
            if current is None and remove:
                return Outcome(thing_id, Category.UNCHANGED, message="the array doesn't exist")
            conditions = Conditions(if_match=etag) if etag else Conditions(if_none_match="*")
            if dry_run:
                outcome = _planned(thing_id, "PUT", target, updated, conditions)
                outcome.detail["before"] = current
                return outcome
            try:
                result = client.put(target, json=updated, conditions=conditions)
                return Outcome(thing_id, Category.OK, result.status)
            except DittoError as e:
                if e.status != 412:
                    raise
                # changed concurrently: read again and recompute
        return Outcome(
            thing_id, Category.CONFLICT, 412, "conflict", f"modified concurrently {conflict_retries + 1} times in a row"
        )

    return operation


def migrate_definition_operation(
    client: DittoClient,
    definition_url: str,
    *,
    payload: Any = None,
    patch_conditions: Mapping[str, str] | None = None,
    initialize_defaults: bool = False,
    dry_run: bool = False,
) -> Operation:
    """Migrate each thing to a new thing definition (WoT Thing Model) via Ditto's ``migrateDefinition``.

    The dry run is done by Ditto (``dry-run=true``): the outcome's ``detail`` is the migration result.
    """
    body: dict[str, Any] = {"thingDefinitionUrl": definition_url}
    if payload is not None:
        body["migrationPayload"] = payload
    if patch_conditions:
        body["patchConditions"] = dict(patch_conditions)
    if initialize_defaults:
        body["initializeMissingPropertiesFromDefaults"] = True

    def operation(thing_id: str) -> Outcome:
        params = {"dry-run": "true"} if dry_run else None
        response = client.post(thing_path(thing_id, "migrateDefinition"), json=body, params=params, retry=True)
        category = Category.PLANNED if dry_run else Category.OK
        return Outcome(thing_id, category, response.status, detail=response.body)

    return operation


def message_operation(
    client: DittoClient,
    subject: str,
    body: Any,
    *,
    feature: str | None = None,
    outbox: bool = False,
    timeout: int | None = None,
    content_type: str | None = None,
    paginate: tuple[str, str] | None = None,
    max_pages: int = 100,
    dry_run: bool = False,
) -> Operation:
    """Send a message to (inbox) or from (outbox) each thing or one of its features.

    ``timeout=0`` doesn't wait for a response (Ditto answers 202). Otherwise the response is in ``detail``.
    ``paginate=(response_field, request_field)`` follows paged answers: as long as a response contains
    ``response_field``, the message is sent again with its value as ``request_field``; ``detail`` is then the
    list of all responses.
    """
    box = "outbox" if outbox else "inbox"
    if paginate and not isinstance(body, dict | None):
        raise DittoctlError("--paginate needs a JSON object as message payload (or none)")

    def send(target: str, payload: Any) -> Any:
        params = {"timeout": str(timeout)} if timeout is not None else None
        if isinstance(payload, str | bytes) and content_type and "json" not in content_type:
            return client.post(target, content=payload, content_type=content_type, params=params)
        return client.post(target, json=payload, content_type=content_type, params=params)

    def operation(thing_id: str) -> Outcome:
        path = f"features/{feature}/{box}/messages/{subject}" if feature else f"{box}/messages/{subject}"
        target = thing_path(thing_id, path)
        if dry_run:
            return _planned(thing_id, "POST", target, body)
        response = send(target, body)
        if not paginate:
            return Outcome(thing_id, Category.OK, response.status, detail=response.body)
        response_field, request_field = paginate
        pages = [response.body]
        while isinstance(response.body, dict) and response.body.get(response_field) and len(pages) < max_pages:
            response = send(target, {**(body or {}), request_field: response.body[response_field]})
            pages.append(response.body)
        if isinstance(response.body, dict) and response.body.get(response_field):
            return Outcome(
                thing_id,
                Category.FAILED,
                response.status,
                "pagination",
                f"stopped after --max-pages {max_pages} with more pages left",
                detail=pages,
            )
        return Outcome(thing_id, Category.OK, response.status, detail=pages)

    return operation

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
"""Writing things: single-thing commands and bulk commands over a selection."""

from __future__ import annotations

import difflib
import json
import sys
from typing import Any

import click

from dittoctl.cli import output
from dittoctl.cli.api_cmd import read_data
from dittoctl.cli.bulk_options import (
    WriteOptions,
    confirm,
    execute,
    pop_selection,
    read_json,
    select,
    selector_options,
    write_options,
)
from dittoctl.cli.options import conditional_options, pop_conditions, protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.cli.things_cmd import things_group
from dittoctl.core.conditions import Conditions, IfEqual
from dittoctl.core.jsonops import (
    NO_CHANGE,
    contains_array,
    deep_equal,
    equality,
    json_diff,
    merge_patch_diff,
    nested,
    segments,
)
from dittoctl.core.things import get_thing, get_things, thing_path
from dittoctl.core.writes import (
    array_operation,
    delete_operation,
    merge_operation,
    migrate_definition_operation,
    put_operation,
)
from dittoctl.errors import AbortedError, CheckFailedError, DittoctlError, DittoError
from dittoctl.formats.flatten import get_path


def _bulk_conditions(kwargs: dict[str, Any]) -> Conditions:
    """Conditions of a bulk write; If-Equal defaults to 'skip' so that re-runs don't produce no-op events."""
    conditions = pop_conditions(kwargs)
    return conditions if conditions.if_equal else conditions.replace(if_equal=IfEqual.SKIP)


def _check_stdin(selection_ids_file: str | None, *values: str | None) -> None:
    if selection_ids_file == "-" and "@-" in values:
        raise click.UsageError("stdin can't provide both the thing ids (--ids-file -) and the data (@-)")


# --- bulk writes ------------------------------------------------------------------------------


@things_group.command("patch")
@click.argument("path")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@click.option("-d", "--data", "data", required=True, metavar="JSON|@FILE|@-", help="The merge patch to apply.")
@click.option("--replace-array", is_flag=True, help="Allow arrays in the patch (they replace the whole array).")
@selector_options
@conditional_options
@write_options
@pass_state
def patch(
    state: AppState, path: str, thing_ids: tuple[str, ...], data: str, replace_array: bool, **kwargs: Any
) -> None:
    """Merge-patch (RFC 7396) a part of each selected thing; PATH '/' patches the whole thing.

    Unchanged values are skipped (--if-equal skip) unless --if-equal update is given. Things that don't
    exist are reported as not-found; they are never created.

    \b
    Examples:
      dittoctl things patch attributes/location -d '{"room":"lab"}' org.example:sensor-1
      dittoctl things patch / -d @patch.json -f 'eq(attributes/model,"X1")' --dry-run
      dittoctl things search -f 'exists(features/temp)' -o ids | dittoctl things patch features/temp/properties \\
          -d '{"unit":"°C"}' --ids-file - --yes
    """
    options = WriteOptions.pop(kwargs)
    conditions = _bulk_conditions(kwargs)
    selection = pop_selection(state, thing_ids, kwargs)
    _check_stdin(selection.ids_file, data)
    body = read_json(data)
    if contains_array(body) and not replace_array:
        raise click.UsageError(
            "the patch contains an array, and a merge patch replaces arrays as a whole, dropping existing items. "
            "Use 'things array add|remove' to change items, or pass --replace-array if replacing is intended"
        )
    if segments(path) == [] and not isinstance(body, dict):
        raise click.UsageError("a patch of the whole thing must be a JSON object")
    ids = select(state, selection)
    confirm(state, len(ids), options, "patch")
    execute(
        state, ids, merge_operation(state.client(), path, body, conditions, dry_run=options.dry_run), options, "patch"
    )


@things_group.command("set")
@click.argument("path")
@click.argument("value")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@click.option("--string", "as_string", is_flag=True, help="Treat VALUE as a string even if it is valid JSON.")
@selector_options
@conditional_options
@write_options
@pass_state
def set_(state: AppState, path: str, value: str, thing_ids: tuple[str, ...], as_string: bool, **kwargs: Any) -> None:
    """Set the value at PATH of each selected thing, creating missing parents.

    VALUE is parsed as JSON if possible (42, true, {"a":1}), otherwise taken as a string. Things that don't
    exist are reported as not-found; they are never created.

    \b
    Examples:
      dittoctl things set attributes/location/room lab org.example:sensor-1
      dittoctl things set features/config/properties/interval 60 -f 'eq(attributes/model,"X1")'
    """
    if not segments(path):
        raise click.UsageError("PATH must not be empty; use 'things patch /' to change the whole thing")
    parsed: Any = value
    if not as_string:
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = value
    _merge_at_root(state, thing_ids, nested(path, parsed), "set", kwargs)


@things_group.command("unset")
@click.argument("path")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@selector_options
@conditional_options
@write_options
@pass_state
def unset(state: AppState, path: str, thing_ids: tuple[str, ...], **kwargs: Any) -> None:
    """Remove the value at PATH of each selected thing (absent values are fine, absent things are not-found).

    \b
    Example:
      dittoctl things unset attributes/obsolete -f 'exists(attributes/obsolete)'
    """
    if not segments(path):
        raise click.UsageError("PATH must not be empty; use 'things delete' to delete things")
    _merge_at_root(state, thing_ids, nested(path, None), "unset", kwargs)


def _merge_at_root(state: AppState, thing_ids: tuple[str, ...], body: Any, action: str, kwargs: dict[str, Any]) -> None:
    options = WriteOptions.pop(kwargs)
    conditions = _bulk_conditions(kwargs)
    ids = select(state, pop_selection(state, thing_ids, kwargs))
    confirm(state, len(ids), options, action)
    execute(
        state, ids, merge_operation(state.client(), "/", body, conditions, dry_run=options.dry_run), options, action
    )


@things_group.group("array")
def array_group() -> None:
    """Add items to, or remove them from, an array in each selected thing, without losing concurrent changes."""


def _array_command(remove: bool) -> Any:
    name = "remove" if remove else "add"
    as_set_option = (
        (lambda f: f)
        if remove
        else click.option("--as-set", is_flag=True, help="Only add items that aren't present yet.")
    )

    @array_group.command(name)
    @click.argument("path")
    @click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
    @click.option("--items", required=True, metavar="JSON|@FILE", help="A JSON array of the items.")
    @as_set_option
    @click.option(
        "--compare",
        type=click.Choice(["deep", "json"]),
        default="deep",
        show_default=True,
        help="Item equality: 'deep' (1 equals 1.0) or 'json' (canonical text).",
    )
    @click.option(
        "--conflict-retries",
        type=click.IntRange(min=0),
        default=3,
        show_default=True,
        help="How often to re-read and retry when the array was changed concurrently.",
    )
    @selector_options
    @write_options
    @pass_state
    def command(
        state: AppState,
        path: str,
        thing_ids: tuple[str, ...],
        items: str,
        compare: str,
        conflict_retries: int,
        as_set: bool = False,
        **kwargs: Any,
    ) -> None:
        options = WriteOptions.pop(kwargs)
        selection = pop_selection(state, thing_ids, kwargs)
        _check_stdin(selection.ids_file, items)
        values = read_json(items, "--items")
        if not isinstance(values, list):
            raise click.BadParameter("must be a JSON array", param_hint="--items")
        ids = select(state, selection)
        confirm(state, len(ids), options, f"{name} items for")
        operation = array_operation(
            state.client(),
            path,
            values,
            remove=remove,
            as_set=as_set,
            equal=equality(compare),
            conflict_retries=conflict_retries,
            dry_run=options.dry_run,
        )
        execute(state, ids, operation, options, f"array {name}")

    command.help = (
        f"{'Remove every occurrence of' if remove else 'Append'} the --items "
        f"{'from' if remove else 'to'} the array at PATH of each selected thing.\n\n"
        "Each array is read with its ETag and written with If-Match, so concurrent changes are never lost; "
        "things whose array wouldn't change aren't written.\n\n"
        "\b\nExample:\n"
        f"  dittoctl things array {name} attributes/tags --items '[\"maintenance\"]'"
        f"{' --as-set' if not remove else ''} -f 'eq(attributes/building,\"B1\")'"
    )
    return command


_array_command(remove=False)
_array_command(remove=True)


@things_group.command("delete")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@selector_options
@conditional_options
@write_options
@pass_state
def delete(state: AppState, thing_ids: tuple[str, ...], **kwargs: Any) -> None:
    """Delete the selected things. Their policies are kept.

    \b
    Examples:
      dittoctl things delete org.example:sensor-1
      dittoctl things delete -f 'eq(attributes/decommissioned,true)' --dry-run
    """
    options = WriteOptions.pop(kwargs)
    conditions = pop_conditions(kwargs)
    ids = select(state, pop_selection(state, thing_ids, kwargs))
    confirm(state, len(ids), options, "delete", destructive=True)
    execute(state, ids, delete_operation(state.client(), conditions, dry_run=options.dry_run), options, "delete")


def _read_things(source: str) -> dict[str, Any]:
    """Things from NDJSON, a JSON array or a single JSON object, keyed by thingId."""
    text = read_data(source if source.startswith("@") else f"@{source}")
    stripped = text.strip()
    try:
        if stripped.startswith("["):
            items = json.loads(stripped)
        elif stripped.startswith("{") and "\n{" not in stripped:
            items = [json.loads(stripped)]
        else:
            items = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    except ValueError as e:
        raise DittoctlError(f"cannot parse {source}: {e}") from None
    things: dict[str, Any] = {}
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("thingId"), str):
            raise DittoctlError(f"{source}: item {index} is not a thing with a thingId")
        things[item["thingId"]] = item
    return things


@things_group.command("import")
@click.argument("source", metavar="FILE|-")
@click.option(
    "--mode",
    type=click.Choice(["create", "upsert"]),
    default="create",
    show_default=True,
    help="'create' only creates things that don't exist; 'upsert' also replaces existing ones.",
)
@write_options
@pass_state
def import_(state: AppState, source: str, mode: str, **kwargs: Any) -> None:
    """Create (or replace) things from NDJSON or a JSON array, such as a 'things export -o ndjson'.

    Each thing needs a thingId. Importing again is safe: existing things are reported as 'exists' (create) or
    left alone when unchanged (upsert).

    \b
    Examples:
      dittoctl things export -n org.example -o ndjson --out backup.ndjson
      dittoctl --context staging things import backup.ndjson --yes
    """
    options = WriteOptions.pop(kwargs)
    things = _read_things(source)
    conditions = Conditions(if_none_match="*") if mode == "create" else Conditions(if_equal=IfEqual.SKIP)
    output.info(f"Read {len(things)} thing(s) from {source}.")
    confirm(state, len(things), options, "import" if mode == "create" else "upsert")
    execute(
        state,
        list(things),
        put_operation(state.client(), things, conditions, dry_run=options.dry_run),
        options,
        "import",
    )


@things_group.command("verify")
@click.argument("path")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@click.option("--equals", "expected", required=True, metavar="JSON|@FILE", help="The expected value at PATH.")
@click.option(
    "--compare",
    type=click.Choice(["deep", "json"]),
    default="deep",
    show_default=True,
    help="Value equality: 'deep' (1 equals 1.0) or 'json' (canonical text).",
)
@click.option("--failed-out", metavar="FILE", help="Write the things that don't match here (usable as --ids-file).")
@selector_options
@pass_state
def verify(
    state: AppState,
    path: str,
    thing_ids: tuple[str, ...],
    expected: str,
    compare: str,
    failed_out: str | None,
    **kwargs: Any,
) -> None:
    """Check that PATH has the expected value in each selected thing, for example after a bulk change.

    Prints the things that don't match as NDJSON and exits with code 6 if there are any.

    \b
    Example:
      dittoctl things verify features/config/properties/interval --equals 60 -f 'eq(attributes/model,"X1")'
    """
    selection = pop_selection(state, thing_ids, kwargs)
    value = read_json(expected, "--equals")
    equal = equality(compare)
    ids = select(state, selection)
    pointer = "/".join(segments(path))
    seen: set[str] = set()
    counts = {"match": 0, "mismatch": 0, "missing": 0}
    log = open(failed_out, "w", encoding="utf-8") if failed_out else None  # noqa: SIM115
    try:
        if log:
            log.write("# thingId\tresult\tactual\n")
        for thing in get_things(state.client(), ids, fields=f"thingId,{pointer}"):
            thing_id = thing.get("thingId")
            seen.add(thing_id)
            actual = get_path(thing, pointer)
            result = (
                "match"
                if actual is not None and equal(actual, value)
                else ("missing" if actual is None else "mismatch")
            )
            counts[result] += 1
            if result != "match":
                output.line({"thingId": thing_id, "result": result, "actual": actual})
                if log:
                    log.write(f"{thing_id}\t{result}\t{json.dumps(actual, ensure_ascii=False)}\n")
        not_found = [i for i in ids if i not in seen]
        for thing_id in not_found:
            output.line({"thingId": thing_id, "result": "not-found"})
            if log:
                log.write(f"{thing_id}\tnot-found\t\n")
    finally:
        if log:
            log.close()
    summary = ", ".join(f"{k} {v}" for k, v in counts.items()) + f", not found {len(not_found)}"
    output.info(f"Verified {len(ids)} thing(s): {summary}")
    if counts["mismatch"] or counts["missing"] or not_found:
        raise CheckFailedError(f"{len(ids) - counts['match']} of {len(ids)} thing(s) don't have the expected value")


@things_group.command("migrate-definition")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@click.option("--definition", required=True, metavar="TM_URL", help="URL of the new WoT Thing Model.")
@click.option("--payload", metavar="JSON|@FILE", help="Attributes/features to merge, may use {{ thing-json:... }}.")
@click.option(
    "--patch-condition",
    "patch_conditions",
    multiple=True,
    metavar="PATH=RQL",
    help="Only merge the payload at PATH if the RQL matches, e.g. features/temp=not(exists(features/temp)).",
)
@click.option("--init-defaults", is_flag=True, help="Initialize missing properties from the model's defaults.")
@selector_options
@write_options
@pass_state
def migrate_definition(
    state: AppState,
    thing_ids: tuple[str, ...],
    definition: str,
    payload: str | None,
    patch_conditions: tuple[str, ...],
    init_defaults: bool,
    **kwargs: Any,
) -> None:
    """Move each selected thing to a new thing definition (Thing Model version), optionally updating it.

    --dry-run lets Ditto compute the result without applying it (Ditto 3.7+).

    \b
    Example:
      dittoctl things migrate-definition --definition https://models.example.org/sensor-2.0.0.tm.jsonld \\
          --init-defaults -f 'eq(definition,"https://models.example.org/sensor-1.0.0.tm.jsonld")' --dry-run
    """
    options = WriteOptions.pop(kwargs)
    selection = pop_selection(state, thing_ids, kwargs)
    conditions = {}
    for item in patch_conditions:
        path, sep, rql = item.partition("=")
        if not sep or not path:
            raise click.BadParameter(f"expected PATH=RQL, got '{item}'", param_hint="--patch-condition")
        key = path if path.startswith("thing:") else "thing:/" + path.strip("/")
        conditions[key] = rql
    ids = select(state, selection)
    confirm(state, len(ids), options, "migrate the definition of")
    operation = migrate_definition_operation(
        state.client(),
        definition,
        payload=read_json(payload, "--payload") if payload else None,
        patch_conditions=conditions,
        initialize_defaults=init_defaults,
        dry_run=options.dry_run,
    )
    execute(state, ids, operation, options, "migrate definition")


# --- single-thing writes ----------------------------------------------------------------------


@things_group.command("create")
@click.argument("thing_id", required=False)
@click.option("-d", "--data", metavar="JSON|@FILE|@-", help="The thing JSON (attributes, features, ...).")
@click.option(
    "--definition",
    metavar="URL|NS:NAME:VERSION",
    help="Thing definition; a WoT Thing Model URL makes Ditto generate the thing's skeleton.",
)
@click.option("--policy-id", help="Use this existing policy instead of a new one.")
@protected_write()
@pass_state
def create(
    state: AppState, thing_id: str | None, data: str | None, definition: str | None, policy_id: str | None
) -> None:
    """Create a thing; fails if it already exists. Without THING_ID, Ditto generates the id.

    \b
    Examples:
      dittoctl things create org.example:sensor-1 -d '{"attributes":{"room":"lab"}}'
      dittoctl things create org.example:lamp-1 --definition https://example.org/models/lamp-1.0.0.tm.jsonld
    """
    body = read_json(data) if data else {}
    if not isinstance(body, dict):
        raise click.BadParameter("must be a JSON object", param_hint="--data")
    if definition:
        body["definition"] = definition
    if policy_id:
        body["policyId"] = policy_id
    client = state.client()
    if thing_id:
        response = client.put(thing_path(thing_id), json=body, conditions=Conditions(if_none_match="*"))
    else:
        response = client.post("/api/2/things", json=body)
    output.emit(response.body)


@things_group.command("put")
@click.argument("thing_id")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The complete thing JSON.")
@conditional_options
@protected_write()
@pass_state
def put(state: AppState, thing_id: str, data: str, **kwargs: Any) -> None:
    """Create or completely replace a thing.

    \b
    Example:
      dittoctl things put org.example:sensor-1 -d @sensor-1.json --if-match rev:7
    """
    conditions = pop_conditions(kwargs)
    body = read_json(data)
    response = state.client().put(thing_path(thing_id), json=body, conditions=conditions)
    if response.body is not None:
        output.emit(response.body)
    else:
        output.info(f"Replaced {thing_id}.")


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@things_group.command("edit")
@click.argument("thing_id")
@click.option("--path", help="Only edit this part, e.g. attributes.")
@protected_write()
@pass_state
def edit(state: AppState, thing_id: str, path: str | None) -> None:
    """Edit a thing in $EDITOR; the changes are sent as a merge patch with If-Match.

    If the thing was changed by someone else in the meantime, nothing is written.
    """
    client = state.client()
    response = get_thing(client, thing_id, path=path)
    original = response.body
    edited_text = click.edit(_pretty(original), extension=".json", require_save=True)
    if edited_text is None:
        output.info("No changes.")
        return
    try:
        edited = json.loads(edited_text)
    except ValueError as e:
        raise DittoctlError(f"the edited JSON is invalid, nothing was written: {e}") from None
    patch_body = merge_patch_diff(original, edited)
    if patch_body is NO_CHANGE:
        output.info("No changes.")
        return
    if not isinstance(original, dict) or not isinstance(edited, dict):
        # a scalar or array at --path: replace it
        client.put(thing_path(thing_id, path), json=edited, conditions=Conditions(if_match=response.etag))
    else:
        try:
            client.patch(thing_path(thing_id, path), json=patch_body, conditions=Conditions(if_match=response.etag))
        except DittoError as e:
            if e.status == 412 and not e.condition_failed:
                raise AbortedError(f"{thing_id} was changed in the meantime; nothing was written. Edit again") from None
            raise
    output.info(f"Updated {thing_id}.")


@things_group.command("diff")
@click.argument("thing_id")
@click.option("--file", "file", required=True, metavar="FILE|-", help="Local JSON to compare with.")
@click.option("--path", help="Compare only this part of the thing.")
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(["text", "json"]),
    help='Output format: a unified diff, or a JSON list of {"op", "path", "old", "new"} with op add, remove or '
    "replace and old being the value in Ditto (default: text; agent mode: json).",
)
@click.pass_context
def diff(ctx: click.Context, thing_id: str, file: str, path: str | None, output_format: str | None) -> None:
    """Show the differences between a local JSON file and the thing in Ditto (exit code 6 if they differ)."""
    state = ctx.find_object(AppState)
    assert state is not None
    remote = get_thing(state.client(), thing_id, path=path).body
    local = read_json(file if file.startswith("@") else f"@{file}", "--file")
    if (output_format or ("json" if output.agent_mode() else "text")) == "json":
        changes = json_diff(remote, local)
        output.emit(changes)
        if changes:
            raise CheckFailedError(f"{len(changes)} difference(s) between {thing_id} and {file}")
        return
    if deep_equal(local, remote):
        output.info("No differences.")
        return
    lines = difflib.unified_diff(
        _pretty(remote).splitlines(keepends=True),
        _pretty(local).splitlines(keepends=True),
        fromfile=f"ditto:{thing_id}{'/' + path.strip('/') if path else ''}",
        tofile=file,
    )
    sys.stdout.writelines(lines)
    raise CheckFailedError(f"{thing_id} and {file} differ")

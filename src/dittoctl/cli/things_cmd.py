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
"""``dittoctl things``: read, search, count, export and watch things."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from typing import Any, TextIO, TypeVar

import click
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from dittoctl.cli import output
from dittoctl.cli.api_cmd import read_data
from dittoctl.cli.options import all_option, conditional_options, duration_option, pop_conditions
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core import rql
from dittoctl.core.fields import field_stats
from dittoctl.core.search import MAX_PAGE_SIZE, Transport, count_things, find_things
from dittoctl.core.streams import Limited, Timeboxed
from dittoctl.core.things import get_thing, get_things, thing_description, thing_history, watch_things
from dittoctl.core.wot import compact_thing_description, thing_description_with_features
from dittoctl.formats import ITEM_FORMATS, Columns, write_items, write_ndjson

F = TypeVar("F", bound=Callable[..., Any])


# --- shared options ---------------------------------------------------------------------------


def filter_options(f: F) -> F:
    f = click.option("--no-validate", is_flag=True, help="Send the filter as is, without checking it locally first.")(f)
    f = click.option("-f", "--filter", "rql_filter", metavar="RQL", help="RQL filter; @file reads it from a file.")(f)
    return f


def namespaces_option(f: F) -> F:
    return click.option(
        "-n",
        "--namespaces",
        multiple=True,
        metavar="NS[,NS]",
        help="Namespaces to search in (default: the context's namespaces, else all). Repeatable.",
    )(f)


def resolve_filter(value: str | None, validate: bool) -> str | None:
    if not value:
        return None
    text = read_data(value).strip()
    if not validate:
        return text
    try:
        node = rql.parse(text)
    except rql.RqlError as e:
        raise click.BadParameter("\n" + e.render(), param_hint="--filter") from None
    for warning in rql.warnings(node):
        output.warn(warning)
    return rql.compact(node)


def resolve_namespaces(state: AppState, values: tuple[str, ...]) -> list[str]:
    namespaces = [ns.strip() for value in values for ns in value.split(",") if ns.strip()]
    return namespaces or state.context().namespaces


def transport_option(f: F) -> F:
    return click.option(
        "--transport",
        type=click.Choice([t.value for t in Transport]),
        default=Transport.AUTO.value,
        show_default=True,
        help="How results are fetched: 'paging' through the search cursor, or Ditto's SSE search 'sse' stream. "
        "'auto' streams when only thing ids are needed (-o ids) and the context allows it, else it pages.",
    )(f)


def effective_fields(fields: str | None, output_format: str | None) -> str | None:
    """With ``-o ids`` and no explicit fields, only the thing id is fetched."""
    return "thingId" if fields is None and output_format == "ids" else fields


def tabular_options(f: F) -> F:
    options = [
        click.option("--columns", metavar="PATH[,PATH]", help="Fixed columns (paths like attributes/location)."),
        click.option(
            "--discover-rows",
            type=int,
            default=100,
            show_default=True,
            help="Rows to inspect for column discovery; 0 inspects all (buffers the whole result).",
        ),
        click.option("--short-headers", is_flag=True, help="Use the shortest unambiguous path suffix as header."),
        click.option("--delimiter", default=",", show_default=True, help="CSV delimiter."),
        click.option("--no-header", is_flag=True, help="Leave out the CSV header row."),
        click.option(
            "--excel", is_flag=True, help="CSV for Excel: UTF-8 BOM, timestamps as 'YYYY-MM-DD HH:MM:SS' (UTC)."
        ),
        click.option(
            "--out",
            type=click.Path(dir_okay=False, writable=True, allow_dash=True),
            help="Write to this file instead of stdout.",
        ),
    ]
    for option in reversed(options):
        f = option(f)
    return f


@contextmanager
def open_output(path: str | None, excel: bool) -> Iterator[TextIO]:
    if path and path != "-":
        with open(path, "w", encoding="utf-8-sig" if excel else "utf-8", newline="") as f:
            yield f
        return
    if excel:
        sys.stdout.write("﻿")
    yield sys.stdout


def emit_items(items: Iterable[Any], fmt: str, opts: dict[str, Any]) -> int:
    columns = Columns(
        explicit=[c.strip() for c in opts["columns"].split(",") if c.strip()] if opts.get("columns") else None,
        discover_rows=opts.get("discover_rows", 100),
        short=opts.get("short_headers", False),
    )
    with open_output(opts.get("out"), opts.get("excel", False) and fmt == "csv") as out:
        return write_items(
            items,
            fmt,
            out,
            columns=columns,
            delimiter=opts.get("delimiter", ","),
            header=not opts.get("no_header", False),
            excel=opts.get("excel", False),
            compact=output.agent_mode(),
            warn=output.warn,
        )


def _default_format(opts: dict[str, Any]) -> str:
    to_terminal = not opts.get("out") or opts["out"] == "-"
    return "table" if to_terminal and sys.stdout.isatty() else "ndjson"


# --- commands ---------------------------------------------------------------------------------


@click.group("things")
def things_group() -> None:
    """Read, search, count, export and watch things."""


@things_group.command("get")
@click.argument("thing_ids", nargs=-1, required=True, metavar="THING_ID...")
@click.option("--path", help="Only this part of the thing, e.g. attributes/location or features/temp/properties.")
@click.option("--fields", help="Field selector, e.g. thingId,attributes/location,features/temp/properties/value.")
@click.option("--at-revision", type=int, help="Read the thing as it was at this revision (needs Ditto history).")
@click.option("--at-time", metavar="TIMESTAMP", help="Read the thing as it was at this ISO-8601 time.")
@click.option(
    "--live",
    is_flag=True,
    help="Ask the device (live channel) instead of the twin; see --live-condition, --live-timeout-strategy.",
)
@click.option(
    "--live-timeout",
    type=click.IntRange(1, 60),
    metavar="SECONDS",
    help="With --live: how long to wait for the device (Ditto's default: 10s).",
)
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(("json", "table", "ndjson", "csv")),
    default="json",
    show_default=True,
    help="Output format.",
)
@conditional_options
@pass_state
def get(
    state: AppState,
    thing_ids: tuple[str, ...],
    path: str | None,
    fields: str | None,
    at_revision: int | None,
    at_time: str | None,
    live: bool,
    live_timeout: int | None,
    output_format: str,
    **kwargs: Any,
) -> None:
    """Retrieve one or more things.

    \b
    Examples:
      dittoctl things get org.example:sensor-1
      dittoctl things get org.example:sensor-1 --path attributes/location
      dittoctl things get org.example:sensor-1 --at-revision 42
      dittoctl things get org.example:sensor-1 org.example:sensor-2 --fields thingId,attributes -o table
    """
    conditions = pop_conditions(kwargs)
    client = state.client()
    if len(thing_ids) > 1:
        if path or at_revision is not None or at_time or live or not conditions.is_empty():
            raise click.UsageError("--path, --at-revision, --at-time, --live and conditions need a single thing id")
        count = emit_items(get_things(client, list(thing_ids), fields=fields), output_format, {})
        if count < len(thing_ids):
            output.warn(f"{len(thing_ids) - count} of {len(thing_ids)} things were not found or not visible")
        return
    response = get_thing(
        client,
        thing_ids[0],
        path=path,
        fields=fields,
        at_revision=at_revision,
        at_timestamp=at_time,
        live=live,
        live_timeout=live_timeout,
        conditions=conditions,
    )
    if response.status == 304:
        output.info("Not modified (the ETag matches).")
        return
    if output_format == "json":
        output.emit(response.body)
    else:
        emit_items([response.body], output_format, {})


@things_group.command("search")
@filter_options
@namespaces_option
@click.option("--fields", help="Field selector, e.g. thingId,attributes/location,_modified.")
@click.option("--sort", metavar="[+-]PATH[,...]", help="Sort order, e.g. -_modified or +attributes/name.")
@click.option("--limit", type=click.IntRange(min=1), help="Stop after this many things.")
@click.option(
    "--page-size",
    type=click.IntRange(1, MAX_PAGE_SIZE),
    default=MAX_PAGE_SIZE,
    show_default=True,
    help="Things per request.",
)
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(ITEM_FORMATS),
    help="Output format (default: table on a terminal, ndjson otherwise).",
)
@all_option
@transport_option
@tabular_options
@pass_state
def search(
    state: AppState,
    rql_filter: str | None,
    no_validate: bool,
    namespaces: tuple[str, ...],
    fields: str | None,
    sort: str | None,
    limit: int | None,
    page_size: int,
    output_format: str | None,
    all_items: bool,
    transport: str,
    **opts: Any,
) -> None:
    """Search things with RQL, following the result cursor through all pages.

    \b
    Examples:
      dittoctl things search -f 'eq(attributes/manufacturer,"ACME")' --fields thingId,attributes
      dittoctl things search -f 'gt(_modified,"2026-11-01T00:00:00Z")' --sort -_modified --limit 20
      dittoctl things search -n org.example -o ids > ids.txt
    """
    output_format = output_format or _default_format(opts)
    default_limit = output.agent_limit(limit, all_items, to_file=_to_file(opts))
    items: Iterable[Any] = find_things(
        state.client(),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        namespaces=resolve_namespaces(state, namespaces),
        fields=effective_fields(fields, output_format),
        sort=sort,
        limit=default_limit + 1 if default_limit else limit,
        page_size=page_size,
        transport=Transport(transport),
        streaming_allowed=state.context().search_streaming,
    )
    if default_limit:
        items = Limited(items, default_limit)
    emit_items(items, output_format, opts)
    if isinstance(items, Limited) and items.more:
        output.more_results("things", items.limit, "Narrow the filter, use --limit N or --all, or 'things count'.")


def _to_file(opts: dict[str, Any]) -> bool:
    return opts.get("out") not in (None, "-")


@things_group.command("export")
@filter_options
@namespaces_option
@click.option("--fields", help="Field selector, e.g. thingId,attributes,features/temp/properties.")
@click.option("--sort", metavar="[+-]PATH[,...]", help="Sort order, e.g. +thingId.")
@click.option("--limit", type=click.IntRange(min=1), help="Stop after this many things.")
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(("csv", "ndjson", "json", "ids")),
    default="csv",
    show_default=True,
    help="Output format.",
)
@click.option("--no-progress", is_flag=True, help="Don't count the things first or show progress.")
@all_option
@transport_option
@tabular_options
@pass_state
def export(
    state: AppState,
    rql_filter: str | None,
    no_validate: bool,
    namespaces: tuple[str, ...],
    fields: str | None,
    sort: str | None,
    limit: int | None,
    output_format: str,
    no_progress: bool,
    all_items: bool,
    transport: str,
    **opts: Any,
) -> None:
    """Export search results to a file, streaming: memory use stays flat regardless of the number of things.

    \b
    Examples:
      dittoctl things export -f 'exists(features/temp)' --fields thingId,features/temp/properties --out temp.csv
      dittoctl things export -n org.example -o ndjson --out backup.ndjson
    """
    client = state.client()
    rql_filter = resolve_filter(rql_filter, not no_validate)
    ns = resolve_namespaces(state, namespaces)
    default_limit = output.agent_limit(limit, all_items, to_file=_to_file(opts))
    items: Iterable[Any] = find_things(
        client,
        rql_filter=rql_filter,
        namespaces=ns,
        fields=effective_fields(fields, output_format),
        sort=sort,
        limit=default_limit + 1 if default_limit else limit,
        transport=Transport(transport),
        streaming_allowed=state.context().search_streaming,
    )
    if default_limit:
        items = Limited(items, default_limit)
    show_progress = not no_progress and sys.stderr.isatty()
    if not show_progress:
        count = emit_items(items, output_format, opts)
    else:
        total = count_things(client, rql_filter=rql_filter, namespaces=ns)
        total = min(total, limit) if limit else total
        progress = Progress(
            TextColumn("Exporting"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=Console(emoji=False, file=sys.stderr),
            transient=True,
        )
        with progress:
            task = progress.add_task("export", total=total)

            def tracked(source: Iterable[Any]) -> Iterator[Any]:
                for item in source:
                    yield item
                    progress.advance(task)

            count = emit_items(tracked(items), output_format, opts)
    target = opts.get("out") if _to_file(opts) else "stdout"
    output.info(f"Exported {count} things to {target}.")
    if isinstance(items, Limited) and items.more:
        output.more_results("things", items.limit, "Export to a file with --out, or use --limit N or --all.")


@things_group.command("count")
@filter_options
@namespaces_option
@pass_state
def count(state: AppState, rql_filter: str | None, no_validate: bool, namespaces: tuple[str, ...]) -> None:
    """Count the things matching an RQL filter."""
    total = count_things(
        state.client(),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        namespaces=resolve_namespaces(state, namespaces),
    )
    click.echo(total)


@things_group.command("fields")
@filter_options
@namespaces_option
@click.option(
    "--sample",
    type=click.IntRange(1, 10_000),
    default=100,
    show_default=True,
    help="How many matching things to inspect: the first ones Ditto returns, not a random sample.",
)
@click.option("--path", metavar="PATH", help="Only paths below this one, e.g. attributes or features/temp.")
@click.option(
    "--examples", type=click.IntRange(0, 20), default=3, show_default=True, help="Distinct example values per path."
)
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(("table", "json", "ndjson", "csv")),
    help="Output format (default: table on a terminal, ndjson otherwise).",
)
@pass_state
def fields(
    state: AppState,
    rql_filter: str | None,
    no_validate: bool,
    namespaces: tuple[str, ...],
    sample: int,
    path: str | None,
    examples: int,
    output_format: str | None,
) -> None:
    """Show which paths the matching things have, with JSON types, frequency and example values.

    Ditto things are schemaless: this shows what to filter on (RQL) and which fields to select, also for
    things without a WoT model (for those, see 'things td'). Each line has path, types, count, share (of the
    inspected things) and examples.

    \b
    Examples:
      dittoctl things fields -n org.example
      dittoctl things fields -f 'eq(attributes/model,"X1")' --path features --sample 500
    """
    things = find_things(
        state.client(),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        namespaces=resolve_namespaces(state, namespaces),
        fields=path.strip("/") if path else None,
        limit=sample,
    )
    stats, total = field_stats(things, max_examples=examples)
    output.info(f"Inspected {total} thing(s).")
    rows = [s.to_json(total) for s in stats]
    fmt = output_format or _default_format({})
    if fmt == "json":
        output.emit(rows)
    else:
        emit_items(rows, fmt, {"columns": "path,types,count,share,examples"} if fmt in ("table", "csv") else {})


@things_group.command("watch")
@filter_options
@namespaces_option
@click.option("--ids", metavar="ID[,ID]", help="Only these things.")
@click.option("--fields", help="Fields of each change to show (default: the changed parts).")
@click.option("--extra-fields", help="Unchanged fields to add to each change, e.g. attributes/location.")
@duration_option("watching")
@click.option("--max-events", type=click.IntRange(min=1), help="Stop after this many changes.")
@pass_state
def watch(
    state: AppState,
    rql_filter: str | None,
    no_validate: bool,
    namespaces: tuple[str, ...],
    ids: str | None,
    fields: str | None,
    extra_fields: str | None,
    duration: float | None,
    max_events: int | None,
) -> None:
    """Follow thing changes as they happen, one JSON object per line. Stop with Ctrl+C, --duration or --max-events.

    \b
    Examples:
      dittoctl things watch -n org.example
      dittoctl things watch -f 'exists(features/temp)' --fields thingId,features/temp/properties/value
      dittoctl things watch --ids org.example:sensor-1 --max-events 1 --duration 2m
    """
    events = watch_things(
        state.client(),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        # the context's default namespaces would hide explicitly given things of other namespaces
        namespaces=resolve_namespaces(state, namespaces) if namespaces or not ids else None,
        thing_ids=[i.strip() for i in ids.split(",") if i.strip()] if ids else None,
        fields=fields,
        extra_fields=extra_fields,
    )
    bounded = Timeboxed(events, duration=output.agent_duration(duration, max_events), max_items=max_events)
    limits = [
        f"for {bounded.duration:g}s" if bounded.duration else "",
        f"for {max_events} changes" if max_events else "",
    ]
    output.info(f"Watching for changes {' or '.join(x for x in limits if x) or 'until Ctrl+C'}.")
    count = 0
    with suppress(KeyboardInterrupt):
        count = write_ndjson(bounded, sys.stdout, flush=True)
    if bounded.stopped == "duration":
        output.info(f"Stopped after {bounded.duration:g}s with {count} change(s) (--duration).")


@things_group.command("history")
@click.argument("thing_id")
@click.option("--from-revision", type=int, help="First revision; negative counts back from the current one.")
@click.option("--to-revision", type=int, help="Last revision; 0 is the current one, negative counts back.")
@click.option("--from-time", metavar="TIMESTAMP", help="First point in time (ISO-8601).")
@click.option("--to-time", metavar="TIMESTAMP", help="Last point in time (ISO-8601).")
@click.option(
    "--fields",
    default="thingId,_revision,_modified,attributes,features",
    show_default=True,
    help="Fields of each change; add _context for the command that caused it.",
)
@click.option("-f", "--filter", "rql_filter", metavar="RQL", help="Only states matching this filter.")
@click.option("--limit", type=click.IntRange(min=1), help="Stop after this many changes.")
@all_option
@pass_state
def history(
    state: AppState,
    thing_id: str,
    from_revision: int | None,
    to_revision: int | None,
    from_time: str | None,
    to_time: str | None,
    fields: str,
    rql_filter: str | None,
    limit: int | None,
    all_items: bool,
) -> None:
    """Show the changes of a thing per revision as NDJSON, oldest first (needs history retention in Ditto).

    Each line has the changed parts only, like 'things watch'; 'things get --at-revision N' shows the
    complete thing at a revision.

    \b
    Examples:
      dittoctl things history org.example:sensor-1 --from-revision -10
      dittoctl things history org.example:sensor-1 --from-time 2026-11-01T00:00:00Z --to-time 2026-11-02T00:00:00Z
    """
    if from_revision is None and from_time is None:
        raise click.UsageError("pass --from-revision or --from-time")
    if from_revision is not None and from_time is not None:
        raise click.UsageError("use either revisions or times")
    events = thing_history(
        state.client(),
        thing_id,
        from_revision=from_revision,
        to_revision=to_revision,
        from_time=from_time,
        to_time=to_time,
        fields=fields,
        rql_filter=resolve_filter(rql_filter, True),
    )
    cap = limit or output.agent_limit(limit, all_items)
    states: Iterable[Any] = Limited(events, cap) if cap else events
    with suppress(KeyboardInterrupt):
        write_ndjson(states, sys.stdout, flush=True)
    if isinstance(states, Limited) and states.more and not limit:
        output.more_results("changes", states.limit, "Narrow --from/--to, use --limit N or --all.")


@things_group.command("td")
@click.argument("thing_id")
@click.option("--feature", help="The Thing Description of this feature instead.")
@click.option(
    "--with-features",
    is_flag=True,
    help="Add the Thing Descriptions of all the thing's features, under 'features'.",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Only titles, descriptions, data schemas and the path of each property, action and event; "
    "single-line JSON when piped.",
)
@click.option(
    "--no-schema-descriptions",
    is_flag=True,
    help="With --compact: leave out the descriptions inside data schemas (those of properties, actions and "
    "events stay).",
)
@pass_state
def td(
    state: AppState,
    thing_id: str,
    feature: str | None,
    with_features: bool,
    compact: bool,
    no_schema_descriptions: bool,
) -> None:
    """Show the WoT Thing Description Ditto generates from the thing's definition (a Thing Model URL).

    --compact leaves out what follows from Ditto's conventions (forms, security, error schemas) and
    lists repeated parts once, which makes the description 2 to 12 times smaller, e.g. for an LLM. Paths
    are relative to the thing, or to features/<name> for a feature's properties, actions and events. A
    feature described exactly like an earlier one is shown as {"sameAs": "<feature>"}, a repeated data
    schema as {"$ref": "#/<JSON pointer to the first one>"}.

    \b
    Examples:
      dittoctl things td org.example:lamp-1
      dittoctl things td org.example:lamp-1 --feature Spot1
      dittoctl things td org.example:lamp-1 --with-features --compact
    """
    if feature and with_features:
        raise click.UsageError("use either --feature or --with-features")
    client = state.client()
    if with_features:
        description = thing_description_with_features(client, thing_id)
    else:
        description = thing_description(client, thing_id, feature)
    if no_schema_descriptions and not compact:
        raise click.UsageError("--no-schema-descriptions needs --compact")
    if compact:
        compacted = compact_thing_description(description, schema_descriptions=not no_schema_descriptions)
        output.emit(compacted, "json" if sys.stdout.isatty() else "ndjson")
    else:
        output.emit(description)

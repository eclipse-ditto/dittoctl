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
"""``dittoctl connections``: manage Ditto connections to message brokers and HTTP endpoints.

The connections API usually requires Ditto's DevOps credentials, so a separate context is common, e.g.
``dittoctl config add-context prod-devops --url ... --auth basic --username devops``.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from dittoctl.cli import output
from dittoctl.cli.bulk_options import read_json
from dittoctl.cli.options import duration_option, output_option, protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core.connections import (
    CONNECTIONS_PATH,
    connection_path,
    log_key,
    redact_secrets,
    redact_uri,
    send_command,
)
from dittoctl.errors import AbortedError, DittoctlError, DittoError
from dittoctl.formats import write_ndjson

MAX_TABLE_MESSAGE = 200


def _print_table(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*row)
    Console(emoji=False, markup=False, file=sys.stdout, width=None if sys.stdout.isatty() else 300).print(table)


@click.group("connections")
def connections_group() -> None:
    """Manage connections (usually needs Ditto's DevOps login: use a separate context)."""


@connections_group.command("list")
@output_option(("table", "json", "ids"), "table")
@pass_state
def list_(state: AppState, output_format: str) -> None:
    """List all connections. URIs are shown without passwords."""
    connections = state.client().get(CONNECTIONS_PATH).body or []
    if output_format == "json":
        output.emit(connections)
    elif output_format == "ids":
        for connection in connections:
            click.echo(connection.get("id"))
    else:
        _print_table(
            ("ID", "NAME", "TYPE", "STATUS", "URI"),
            [
                (
                    c.get("id", ""),
                    c.get("name", ""),
                    c.get("connectionType", ""),
                    c.get("connectionStatus", ""),
                    redact_uri(c.get("uri", "")),
                )
                for c in connections
            ],
        )


@connections_group.command("get")
@click.argument("connection_id")
@pass_state
def get(state: AppState, connection_id: str) -> None:
    """Retrieve a connection's configuration."""
    output.emit(state.client().get(connection_path(connection_id)).body)


@connections_group.command("create")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The connection JSON.")
@protected_write()
@pass_state
def create(state: AppState, data: str) -> None:
    """Create a connection; fails if it exists. Without an "id" in the JSON, Ditto generates one.

    See 'connections test' to check a connection without creating it.
    """
    connection = read_json(data)
    client = state.client()
    connection_id = connection.get("id") if isinstance(connection, dict) else None
    if not connection_id:
        output.emit(client.post(CONNECTIONS_PATH, json=connection).body)
        return
    # Ditto refuses an id on POST (connectivity:id.notsettable); a PUT creates, but would also replace
    try:
        client.get(connection_path(connection_id))
    except DittoError as e:
        if e.status != 404:
            raise
    else:
        raise DittoctlError(f"connection {connection_id} already exists; use 'connections put' to replace it")
    response = client.put(connection_path(connection_id), json=connection)
    output.emit(response.body if response.body is not None else client.get(connection_path(connection_id)).body)


@connections_group.command("put")
@click.argument("connection_id")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The connection JSON.")
@protected_write()
@pass_state
def put(state: AppState, connection_id: str, data: str) -> None:
    """Create or replace a connection with the given id."""
    response = state.client().put(connection_path(connection_id), json=read_json(data))
    output.info(f"{'Created' if response.status == 201 else 'Updated'} connection {connection_id}.")


@connections_group.command("delete")
@click.argument("connection_id")
@click.option("-y", "--yes", is_flag=True, help="Don't ask for confirmation.")
@protected_write()
@pass_state
def delete(state: AppState, connection_id: str, yes: bool) -> None:
    """Delete a connection."""
    if not yes:
        if not sys.stdin.isatty():
            raise AbortedError("refusing to delete a connection without --yes when not interactive")
        if not click.confirm(f"Delete connection {connection_id}?", default=False):
            raise AbortedError("not confirmed")
    state.client().delete(connection_path(connection_id))
    output.info(f"Deleted connection {connection_id}.")


@connections_group.command("test")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The connection JSON to test.")
@pass_state
def test(state: AppState, data: str) -> None:
    """Check a connection configuration (Ditto connects once, then discards it; nothing is created)."""
    response = state.client().post(CONNECTIONS_PATH, json=read_json(data), params={"dry-run": "true"})
    if response.body is None:
        output.info(f"Connection test succeeded ({response.status}).")
    else:
        output.emit(response.body)


def _command(name: str, description: str) -> None:
    @connections_group.command(name, help=description)
    @click.argument("connection_id")
    @protected_write()
    @pass_state
    def command(state: AppState, connection_id: str) -> None:
        send_command(state.client(), connection_id, name)
        output.info(f"{name}: sent to {connection_id}.")


_command("open", "Open a connection.")
_command("close", "Close a connection.")
_command("reset-metrics", "Reset a connection's metrics.")


@connections_group.command("status")
@click.argument("connection_id")
@output_option(("table", "json"), "table")
@pass_state
def status(state: AppState, connection_id: str, output_format: str) -> None:
    """Show the live status of a connection, its clients, sources and targets."""
    body = state.client().get(connection_path(connection_id, "status")).body or {}
    if output_format == "json":
        output.emit(body)
        return
    click.echo(
        f"connection: {body.get('connectionStatus')} (live: {body.get('liveStatus')})"
        f"{', since ' + body['connectedSince'] if body.get('connectedSince') else ''}"
    )
    rows = []
    for kind in ("clientStatus", "sourceStatus", "targetStatus", "sshTunnelStatus"):
        for entry in body.get(kind, []):
            rows.append(
                (
                    kind.removesuffix("Status"),
                    entry.get("addresses", entry.get("client", "")) or "",
                    entry.get("status", ""),
                    entry.get("statusDetails", ""),
                    entry.get("inStateSince", ""),
                )
            )
    if rows:
        _print_table(("KIND", "ADDRESS/CLIENT", "STATUS", "DETAILS", "SINCE"), [tuple(map(str, r)) for r in rows])


@connections_group.command("metrics")
@click.argument("connection_id")
@pass_state
def metrics(state: AppState, connection_id: str) -> None:
    """Show a connection's message metrics."""
    output.emit(state.client().get(connection_path(connection_id, "metrics")).body)


@connections_group.command("logs")
@click.argument("connection_id")
@click.option("--enable", is_flag=True, help="Enable logging first (Ditto keeps it on for a limited time).")
@click.option("--reset", is_flag=True, help="Clear the logs first.")
@click.option(
    "--follow", is_flag=True, help="Keep polling and print new entries as they appear, until Ctrl+C or --duration."
)
@click.option("--interval", type=float, default=2.0, show_default=True, help="Seconds between polls with --follow.")
@duration_option("following")
@click.option("--no-redact", is_flag=True, help="Show Authorization headers and URI passwords in log messages.")
@output_option(("table", "ndjson"), "table")
@protected_write(lambda params: params["enable"] or params["reset"])
@pass_state
def logs(
    state: AppState,
    connection_id: str,
    enable: bool,
    reset: bool,
    follow: bool,
    interval: float,
    no_redact: bool,
    output_format: str,
    duration: float | None,
) -> None:
    """Show a connection's logs: successful and failed messages per source/target address.

    Ditto's log messages contain the headers of the request that caused a message, including Authorization
    headers; dittoctl masks them unless --no-redact is given. The table shortens long messages; -o ndjson
    shows them completely.

    \b
    Example:
      dittoctl connections logs my-connection --enable --follow -o ndjson
    """
    client = state.client()
    if reset:
        send_command(client, connection_id, "reset-logs")
    if enable:
        send_command(client, connection_id, "enable-logs")
    seen: set[tuple[Any, ...]] = set()

    def poll() -> list[dict[str, Any]]:
        body = client.get(connection_path(connection_id, "logs")).body or {}
        if not body.get("enabledSince") and not enable and not warned:
            output.warn("logging is not enabled for this connection (or it is closed); pass --enable")
            warned.append(True)
        fresh = [e for e in body.get("connectionLogs", []) if log_key(e) not in seen]
        seen.update(log_key(e) for e in fresh)
        if not no_redact:
            fresh = [{**e, "message": redact_secrets(str(e.get("message", "")))} for e in fresh]
        return sorted(fresh, key=lambda e: e.get("timestamp", ""))

    def shorten(text: str) -> str:
        text = " ".join(text.split())
        return text if len(text) <= MAX_TABLE_MESSAGE else text[: MAX_TABLE_MESSAGE - 1] + "…"

    def show(entries: list[dict[str, Any]]) -> None:
        if output_format == "ndjson":
            write_ndjson(entries, sys.stdout, flush=True)
        elif entries:
            _print_table(
                ("TIMESTAMP", "LEVEL", "CATEGORY", "TYPE", "ADDRESS", "ENTITY", "MESSAGE"),
                [
                    (
                        *(str(e.get(k, "")) for k in ("timestamp", "level", "category", "type", "address", "entityId")),
                        shorten(str(e.get("message", ""))),
                    )
                    for e in entries
                ],
            )

    warned: list[bool] = []
    show(poll())
    if not follow:
        return
    limit = output.agent_duration(duration)
    deadline = time.monotonic() + limit if limit else None
    try:
        while deadline is None or time.monotonic() + interval < deadline:
            time.sleep(interval)
            show(poll())
    except KeyboardInterrupt:
        return
    output.info(f"Stopped following after {limit:g}s (--duration).")

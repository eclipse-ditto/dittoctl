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
"""``dittoctl devops``: operate a Ditto installation (needs Ditto's DevOps login, usually a separate context)."""

from __future__ import annotations

import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from dittoctl.cli import output
from dittoctl.cli.bulk_options import read_json
from dittoctl.cli.options import output_option, protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core.devops import (
    SEARCH_SERVICE,
    block_namespace_command,
    get_config,
    get_logging,
    health_lines,
    piggyback,
    piggyback_errors,
    purge_namespace_command,
    purge_results,
    purge_succeeded,
    reindex_command,
    reindex_thing_command,
    set_logging,
    shutdown_namespace_command,
    unblock_namespace_command,
)
from dittoctl.errors import AbortedError, DittoctlError, DittoError

LEVELS = ("trace", "debug", "info", "warn", "error", "off")
SERVICES = ("gateway", "things", "things-search", "policies", "connectivity")


def _table(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*row)
    Console(emoji=False, markup=False, file=sys.stdout, width=None if sys.stdout.isatty() else 200).print(table)


@click.group("devops")
def devops_group() -> None:
    """Operate Ditto: log levels, configuration, piggyback commands, reindexing, namespaces, status.

    These endpoints need Ditto's DevOps login; use a separate context, e.g. 'dittoctl -c prod-devops devops ...'.
    """


@devops_group.group("logging")
def logging_group() -> None:
    """Show and change log levels at runtime."""


@logging_group.command("get")
@click.argument("service", required=False, type=click.Choice(SERVICES))
@output_option(("table", "json"), "table")
@pass_state
def logging_get(state: AppState, service: str | None, output_format: str) -> None:
    """Show the log levels of all services, or of one."""
    body = get_logging(state.client(), service) or {}
    if output_format == "json":
        output.emit(body)
        return
    by_service = {service: body} if service else body
    rows = []
    for name, instances in sorted(by_service.items()):
        for instance, response in sorted((instances or {}).items()):
            for config in response.get("loggerConfigs", []):
                rows.append((name, str(instance), config.get("logger", ""), config.get("level", "")))
    _table(("SERVICE", "INSTANCE", "LOGGER", "LEVEL"), rows)


@logging_group.command("set")
@click.argument("logger")
@click.argument("level", type=click.Choice(LEVELS, case_sensitive=False))
@click.option("--service", type=click.Choice(SERVICES), help="Only this service (default: all).")
@protected_write()
@pass_state
def logging_set(state: AppState, logger: str, level: str, service: str | None) -> None:
    """Set the level of a logger, such as 'org.eclipse.ditto debug'. Takes effect immediately, until a restart."""
    set_logging(state.client(), logger, level, service)
    output.info(f"Set {logger} to {level.lower()} in {service or 'all services'}.")


@devops_group.command("config")
@click.argument("service", required=False, type=click.Choice(SERVICES))
@click.option("--instance", help="Only this instance of the service.")
@click.option("--path", help="Only this part of the configuration, e.g. ditto.gateway.streaming.")
@pass_state
def config(state: AppState, service: str | None, instance: str | None, path: str | None) -> None:
    """Show the runtime configuration of services (large: narrow it down with --path)."""
    if instance and not service:
        raise click.UsageError("--instance needs a SERVICE")
    output.emit(get_config(state.client(), service, instance, path))


@devops_group.command("piggyback")
@click.argument("service", required=False)
@click.option(
    "-d",
    "--data",
    "data",
    required=True,
    metavar="JSON|@FILE|@-",
    help="The piggyback command: targetActorSelection, headers, piggybackCommand.",
)
@click.option("--instance", help="Only this instance of the service.")
@click.option("--timeout", default="10s", show_default=True, help="How long Ditto waits for responses, e.g. 30s.")
@protected_write()
@pass_state
def piggyback_cmd(state: AppState, service: str | None, data: str, instance: str | None, timeout: str) -> None:
    """Send a piggyback command to actors in the Ditto cluster (SERVICE: things, search, connectivity, ...).

    See https://eclipse.dev/ditto/installation-operating.html#piggyback-commands
    """
    response = piggyback(state.client(), read_json(data), service=service, instance=instance, timeout=timeout)
    output.info(f"{response.status}")
    if response.body is not None:
        output.emit(response.body)
    if response.status >= 400 and response.status != 408:
        raise DittoctlError(f"piggyback command failed with {response.status}")
    if errors := piggyback_errors(response.body):
        first = errors[0].get("payload", errors[0])
        reason = first.get("message") or first.get("error") if isinstance(first, dict) else None
        where = errors[0].get("instance") or errors[0].get("serviceName") or "Ditto"
        raise DittoctlError(
            f"{len(errors)} error response(s), e.g. from {where}: {errors[0].get('status')} {reason or ''}".rstrip()
        )


@devops_group.command("reindex")
@click.option("-n", "--namespace", "namespaces", multiple=True, help="Only things of this namespace. Repeatable.")
@click.option("--thing", "thing_ids", multiple=True, metavar="THING_ID", help="Update this thing now. Repeatable.")
@protected_write()
@pass_state
def reindex(state: AppState, namespaces: tuple[str, ...], thing_ids: tuple[str, ...]) -> None:
    """Rebuild search index entries: of single things immediately, or of all things (or namespaces) in the next
    background sync. Ditto doesn't report progress; follow the search service's logs."""
    if namespaces and thing_ids:
        raise click.UsageError("use either --namespace or --thing")
    client = state.client()
    if thing_ids:
        for thing_id in thing_ids:
            piggyback(client, reindex_thing_command(thing_id), service=SEARCH_SERVICE, timeout="0")
        output.info(f"Requested a search index update of {len(thing_ids)} thing(s).")
        return
    response = piggyback(client, reindex_command(namespaces), service=SEARCH_SERVICE)
    if response.status >= 400 and response.status != 408:
        raise DittoctlError(f"reindex request failed with {response.status}: {response.text[:200]}")
    where = f"namespace(s) {', '.join(namespaces)}" if namespaces else "all things"
    output.info(f"Forced a search index update of {where} in the next background sync.")


@devops_group.group("namespace")
def namespace_group() -> None:
    """Namespace operations."""


@namespace_group.command("erase")
@click.argument("namespace")
@click.option("--confirm-namespace", metavar="NAMESPACE", help="Confirm without the prompt (for scripts).")
@click.option(
    "--purge-timeout",
    default="10s",
    show_default=True,
    help="How long Ditto waits for the services to confirm the erasure.",
)
@protected_write()
@pass_state
def namespace_erase(state: AppState, namespace: str, confirm_namespace: str | None, purge_timeout: str) -> None:
    """Erase ALL data of a namespace: things, policies, connections' data and search index entries.

    Runs Ditto's documented sequence: block the namespace, shut down its actors, purge its data from the
    persistence, unblock it. Cannot be undone.
    """
    if confirm_namespace != namespace:
        if confirm_namespace is not None or not sys.stdin.isatty():
            raise AbortedError(f"confirm with --confirm-namespace {namespace}")
        typed = click.prompt(f"This erases ALL data in namespace '{namespace}'. Type the namespace to confirm")
        if typed != namespace:
            raise AbortedError("namespace not confirmed")
    client = state.client()

    def step(name: str, command: dict[str, Any], timeout: str = "10s", expect_timeout: bool = False) -> Any:
        response = piggyback(client, command, timeout=timeout)
        ok = response.status < 300 or (expect_timeout and response.status == 408)
        output.info(f"{name}: {response.status}{'' if ok else ' FAILED'}")
        if not ok:
            raise DittoError(response.status, message=f"{name} failed: {response.text[:300]}")
        return response.body

    step("block", block_namespace_command(namespace))
    try:
        # Ditto never answers the shutdown, so a 408 is expected. The documented timeout=0 is refused by Ditto
        # ("must not be zero if response or acknowledgements are requested"), hence a short timeout.
        step("shutdown", shutdown_namespace_command(namespace), timeout="2s", expect_timeout=True)
        body = step("purge", purge_namespace_command(namespace), timeout=purge_timeout, expect_timeout=True)
        if body is not None and DittoError.is_error_body(body) and body.get("status") == 408:
            # observed with Ditto 3.9.8: all services erase the data and log it, but the gateway's aggregation of
            # their confirmations times out and answers 408 without any results
            raise DittoctlError(
                f"Ditto didn't confirm the erasure of namespace {namespace} within {purge_timeout}. The data may "
                f"have been erased anyway; check, e.g. with 'things count -n {namespace}', and the services' logs "
                "for 'Successfully purged namespace'"
            )
        results = purge_results(body)
        for result in results:
            output.info(f"  {result.get('resourceType')}: {'erased' if purge_succeeded(result) else 'FAILED'}")
        if not results or not all(purge_succeeded(r) for r in results):
            raise DittoctlError(f"the purge of namespace {namespace} was not confirmed for all resource types")
    finally:
        step("unblock", unblock_namespace_command(namespace))
    output.info(f"Namespace {namespace} erased.")


@devops_group.command("status")
@click.option("--health", "with_health", is_flag=True, help="Also show the health of all cluster members.")
@output_option(("text", "json"), "text")
@pass_state
def status(state: AppState, with_health: bool, output_format: str) -> None:
    """Show the Ditto version and gateway status, optionally with the cluster health."""
    client = state.client()
    info = client.get("/status").body or {}
    health = client.get("/status/health").body if with_health else None
    if output_format == "json":
        output.emit({"status": info, **({"health": health} if health is not None else {})})
        return
    for key in ("service-version", "service", "instance", "roles"):
        if key in info:
            value = info[key]
            # /status lists roles either as names or as an object of role -> instances -> details
            value = ", ".join(sorted(value)) if isinstance(value, list | dict) else value
            click.echo(f"{key + ':':<17}{value}")
    if isinstance(health, dict):
        click.echo("")
        for depth, label, state_ in health_lines(health):
            marker = "" if state_ == "UP" else "  <--"
            click.echo(f"{'  ' * depth}{label}: {state_}{marker}")

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
"""``dittoctl policies``: policies, entries, subjects, imports, permission checks and actions."""

from __future__ import annotations

import re
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from dittoctl.cli import output
from dittoctl.cli.bulk_options import WriteOptions, confirm, execute, read_json, write_options
from dittoctl.cli.options import all_option, conditional_options, output_option, pop_conditions, protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.cli.things_cmd import resolve_filter, resolve_namespaces
from dittoctl.core.policies import (
    check_permissions,
    lockout_params,
    policy_ids_of_things,
    policy_path,
    subject_migration_operation,
)
from dittoctl.core.selectors import read_ids_file, unique
from dittoctl.errors import AbortedError, CheckFailedError

allow_lockout_option = click.option(
    "--allow-lockout",
    is_flag=True,
    help="Allow a change that removes your own WRITE permission on the policy (Ditto refuses it otherwise).",
)


@click.group("policies")
def policies_group() -> None:
    """Read and change policies: entries, subjects, imports; check permissions; migrate subjects in bulk."""


@policies_group.command("get")
@click.argument("policy_id")
@click.option("--resolved", is_flag=True, help="Show the effective policy with imports resolved (Ditto 3.9+).")
@click.option("--path", help="Only this part, e.g. entries/owner or imports.")
@output_option(("json", "ndjson"), "json")
@conditional_options
@pass_state
def get(state: AppState, policy_id: str, resolved: bool, path: str | None, output_format: str, **kwargs: Any) -> None:
    """Retrieve a policy."""
    conditions = pop_conditions(kwargs)
    params = {"policy-view": "resolved"} if resolved else None
    segments = [s for s in (path or "").split("/") if s]
    response = state.client().get(policy_path(policy_id, *segments), params=params, conditions=conditions)
    if response.status == 304:
        output.info("Not modified (the ETag matches).")
        return
    output.emit(response.body, output_format)


@policies_group.command("put")
@click.argument("policy_id")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The complete policy JSON.")
@allow_lockout_option
@conditional_options
@protected_write()
@pass_state
def put(state: AppState, policy_id: str, data: str, allow_lockout: bool, **kwargs: Any) -> None:
    """Create or completely replace a policy."""
    conditions = pop_conditions(kwargs)
    response = state.client().put(
        policy_path(policy_id), json=read_json(data), conditions=conditions, params=lockout_params(allow_lockout)
    )
    output.info(f"{'Created' if response.status == 201 else 'Replaced'} policy {policy_id}.")


@policies_group.command("delete")
@click.argument("policy_id")
@click.option("-y", "--yes", is_flag=True, help="Don't ask for confirmation.")
@protected_write()
@pass_state
def delete(state: AppState, policy_id: str, yes: bool) -> None:
    """Delete a policy. Things that still use it become inaccessible."""
    if not yes:
        if not sys.stdin.isatty():
            raise AbortedError("refusing to delete a policy without --yes when not interactive")
        if not click.confirm(f"Delete policy {policy_id}? Things using it become inaccessible", default=False):
            raise AbortedError("not confirmed")
    state.client().delete(policy_path(policy_id))
    output.info(f"Deleted policy {policy_id}.")


@policies_group.command("list")
@click.option("-f", "--filter", "rql_filter", metavar="RQL", help="Filter on things; @file reads it.")
@click.option("--no-validate", is_flag=True, help="Send the filter without checking it locally first.")
@click.option("-n", "--namespaces", multiple=True, metavar="NS[,NS]", help="Namespaces of the things.")
@all_option
@pass_state
def list_(
    state: AppState, rql_filter: str | None, no_validate: bool, namespaces: tuple[str, ...], all_items: bool
) -> None:
    """List the distinct policy ids of the things matching a filter.

    Ditto can't search policies directly, so they are found via the things using them.

    \b
    Example:
      dittoctl policies list -f 'like(policyId,"org.example:customer-*")' > policies.txt
    """
    ids = policy_ids_of_things(
        state.client(),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        namespaces=resolve_namespaces(state, namespaces),
    )
    shown = output.agent_limit(None, all_items) or len(ids)
    for policy_id in ids[:shown]:
        click.echo(policy_id)
    output.info(f"{len(ids)} policies.")
    if len(ids) > shown:
        output.more_results("policies", shown, "Narrow the filter or use --all.")


# --- entries ----------------------------------------------------------------------------------


@policies_group.group("entries")
def entries_group() -> None:
    """Policy entries: who (subjects) may do what (resources)."""


@entries_group.command("list")
@click.argument("policy_id")
@pass_state
def entries_list(state: AppState, policy_id: str) -> None:
    """Show the entries of a policy as a table."""
    entries = state.client().get(policy_path(policy_id, "entries")).body or {}
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in ("LABEL", "SUBJECTS", "RESOURCES"):
        table.add_column(column, overflow="fold")
    for label, entry in entries.items():
        resources = [
            f"{resource} {'+' + ','.join(grants['grant']) if grants.get('grant') else ''}"
            f"{' -' + ','.join(grants['revoke']) if grants.get('revoke') else ''}".strip()
            for resource, grants in entry.get("resources", {}).items()
        ]
        table.add_row(label, "\n".join(entry.get("subjects", {})), "\n".join(resources))
    Console(emoji=False, markup=False, file=sys.stdout, width=None if sys.stdout.isatty() else 200).print(table)


@entries_group.command("get")
@click.argument("policy_id")
@click.argument("label")
@pass_state
def entries_get(state: AppState, policy_id: str, label: str) -> None:
    """Retrieve one entry."""
    output.emit(state.client().get(policy_path(policy_id, "entries", label)).body)


@entries_group.command("put")
@click.argument("policy_id")
@click.argument("label")
@click.option("-d", "--data", required=True, metavar="JSON|@FILE|@-", help="The entry: subjects and resources.")
@allow_lockout_option
@conditional_options
@protected_write()
@pass_state
def entries_put(state: AppState, policy_id: str, label: str, data: str, allow_lockout: bool, **kwargs: Any) -> None:
    """Create or replace one entry."""
    conditions = pop_conditions(kwargs)
    state.client().put(
        policy_path(policy_id, "entries", label),
        json=read_json(data),
        conditions=conditions,
        params=lockout_params(allow_lockout),
    )
    output.info(f"Entry {label} of {policy_id} saved.")


@entries_group.command("delete")
@click.argument("policy_id")
@click.argument("label")
@allow_lockout_option
@protected_write()
@pass_state
def entries_delete(state: AppState, policy_id: str, label: str, allow_lockout: bool) -> None:
    """Delete one entry."""
    state.client().delete(policy_path(policy_id, "entries", label), params=lockout_params(allow_lockout))
    output.info(f"Entry {label} of {policy_id} deleted.")


# --- subjects ---------------------------------------------------------------------------------


@policies_group.group("subjects")
def subjects_group() -> None:
    """Subjects of policy entries: add, remove, and migrate them across many policies."""


@subjects_group.command("add")
@click.argument("policy_id")
@click.argument("label")
@click.argument("subject_id")
@click.option("--type", "subject_type", default="added by dittoctl", show_default=True, help="Subject type.")
@click.option("--expiring-at", metavar="TIMESTAMP", help="ISO-8601 time after which Ditto removes the subject.")
@protected_write()
@pass_state
def subjects_add(
    state: AppState, policy_id: str, label: str, subject_id: str, subject_type: str, expiring_at: str | None
) -> None:
    """Add (or update) a subject of an entry, such as 'integration:my-app' or 'nginx:alice'."""
    body: dict[str, Any] = {"type": subject_type}
    if expiring_at:
        body["expiry"] = expiring_at
    state.client().put(policy_path(policy_id, "entries", label, "subjects", subject_id), json=body)
    output.info(f"Subject {subject_id} saved in {policy_id}/{label}.")


@subjects_group.command("remove")
@click.argument("policy_id")
@click.argument("label")
@click.argument("subject_id")
@allow_lockout_option
@protected_write()
@pass_state
def subjects_remove(state: AppState, policy_id: str, label: str, subject_id: str, allow_lockout: bool) -> None:
    """Remove a subject from an entry."""
    state.client().delete(
        policy_path(policy_id, "entries", label, "subjects", subject_id), params=lockout_params(allow_lockout)
    )
    output.info(f"Subject {subject_id} removed from {policy_id}/{label}.")


@subjects_group.command("migrate")
@click.argument("policy_ids", nargs=-1, metavar="[POLICY_ID]...")
@click.option("--ids-file", metavar="FILE", help="Policy ids, one per line; - reads stdin.")
@click.option("-f", "--filter", "rql_filter", metavar="RQL", help="Migrate the policies of the things matching this.")
@click.option("--no-validate", is_flag=True, help="Send the filter without checking it locally first.")
@click.option("-n", "--namespaces", multiple=True, metavar="NS[,NS]", help="Namespaces of the things for --filter.")
@click.option("--match", "match", required=True, metavar="REGEX", help="Subject ids to migrate (full match).")
@click.option(
    "--template",
    required=True,
    metavar="TEMPLATE",
    help=r"The new subject id; \1 or \g<name> insert groups of --match.",
)
@click.option("--label", "labels", multiple=True, help="Only in entries with this label. Repeatable.")
@click.option("--remove-old", is_flag=True, help="Replace the matching subjects instead of adding next to them.")
@click.option(
    "--conflict-retries",
    type=click.IntRange(min=0),
    default=3,
    show_default=True,
    help="How often to re-read and retry when a policy was changed concurrently.",
)
@allow_lockout_option
@write_options
@pass_state
def subjects_migrate(
    state: AppState,
    policy_ids: tuple[str, ...],
    ids_file: str | None,
    rql_filter: str | None,
    no_validate: bool,
    namespaces: tuple[str, ...],
    match: str,
    template: str,
    labels: tuple[str, ...],
    remove_old: bool,
    conflict_retries: int,
    allow_lockout: bool,
    **kwargs: Any,
) -> None:
    """Add a new subject next to (or instead of) every subject matching --match, with the same permissions.

    Typical when switching identity providers: users keep their permissions under their new subject ids. Each
    policy is written atomically with If-Match; running the migration again changes nothing.

    \b
    Example (add a twin subject for every user of an old IdP, keep the old one for now):
      dittoctl policies subjects migrate -f 'like(policyId,"org.example:customer-*")' \\
          --match 'oldidp:(?P<sub>[0-9a-f-]{36})' --template 'newidp:fed-sub:\\g<sub>' --dry-run
    """
    options = WriteOptions.pop(kwargs)
    try:
        pattern = re.compile(match)
    except re.error as e:
        raise click.BadParameter(str(e), param_hint="--match") from None
    if bool(policy_ids or ids_file) == bool(rql_filter):
        raise click.UsageError("select policies either by id (arguments, --ids-file) or by --filter on things")
    if rql_filter:
        ids = policy_ids_of_things(
            state.client(),
            rql_filter=resolve_filter(rql_filter, not no_validate),
            namespaces=resolve_namespaces(state, namespaces),
        )
    else:
        ids = unique([*policy_ids, *(read_ids_file(ids_file) if ids_file else [])])
    output.info(f"Selected {len(ids)} policies.")
    confirm(state, len(ids), options, "migrate subjects of")

    def show(outcome: Any) -> None:
        if outcome.detail and not options.dry_run:
            for change in outcome.detail:
                output.debug(f"{outcome.thing_id}: {change}")

    operation = subject_migration_operation(
        state.client(),
        pattern,
        template,
        labels=set(labels) or None,
        remove_old=remove_old,
        allow_lockout=allow_lockout,
        conflict_retries=conflict_retries,
        dry_run=options.dry_run,
    )
    execute(
        state, ids, operation, options, "migrate subjects", on_outcome=show if state.verbose else None, noun="policies"
    )


# --- imports ----------------------------------------------------------------------------------


@policies_group.group("imports")
def imports_group() -> None:
    """Policy imports: reuse entries of other policies."""


@imports_group.command("list")
@click.argument("policy_id")
@pass_state
def imports_list(state: AppState, policy_id: str) -> None:
    """Show the imports of a policy."""
    output.emit(state.client().get(policy_path(policy_id, "imports")).body or {})


@imports_group.command("add")
@click.argument("policy_id")
@click.argument("imported_policy_id")
@click.option(
    "--entry",
    "entries",
    multiple=True,
    metavar="LABEL",
    help="Import only this entry (it must be importable). Repeatable; default: all implicit ones.",
)
@protected_write()
@pass_state
def imports_add(state: AppState, policy_id: str, imported_policy_id: str, entries: tuple[str, ...]) -> None:
    """Import the entries of another policy."""
    body = {"entries": list(entries)} if entries else {}
    state.client().put(policy_path(policy_id, "imports", imported_policy_id), json=body)
    output.info(f"{policy_id} imports {imported_policy_id}.")


@imports_group.command("remove")
@click.argument("policy_id")
@click.argument("imported_policy_id")
@protected_write()
@pass_state
def imports_remove(state: AppState, policy_id: str, imported_policy_id: str) -> None:
    """Remove an import."""
    state.client().delete(policy_path(policy_id, "imports", imported_policy_id))
    output.info(f"{policy_id} no longer imports {imported_policy_id}.")


# --- permissions and actions ------------------------------------------------------------------


@policies_group.command("check")
@click.argument("entity_id")
@click.option(
    "--resource",
    "resources",
    multiple=True,
    required=True,
    metavar="RESOURCE",
    help="E.g. thing:/attributes/location, thing:/features/temp, policy:/, message:/. Repeatable.",
)
@click.option(
    "--permission",
    "permissions",
    multiple=True,
    type=click.Choice(["READ", "WRITE"]),
    default=("READ",),
    show_default=True,
    help="Permissions to check. Repeatable.",
)
@click.pass_context
def check(ctx: click.Context, entity_id: str, resources: tuple[str, ...], permissions: tuple[str, ...]) -> None:
    """Check which of the given resources of a thing or policy you may access (Ditto 3.7+).

    Exit code 6 if any check is denied.

    \b
    Example:
      dittoctl policies check org.example:sensor-1 --resource thing:/attributes --resource thing:/features/temp \\
          --permission READ --permission WRITE
    """
    state = ctx.find_object(AppState)
    assert state is not None
    checks = {
        resource: {"resource": resource, "entityId": entity_id, "hasPermissions": list(permissions)}
        for resource in resources
    }
    results = check_permissions(state.client(), checks)
    for resource in resources:
        allowed = results.get(resource)
        click.echo(f"{'allowed' if allowed else 'denied ':8} {resource} ({'+'.join(permissions)})")
    denied = [r for r in resources if not results.get(r)]
    if denied:
        raise CheckFailedError(f"{len(denied)} of {len(resources)} resource(s) denied")


def _token_integration(activate: bool) -> Any:
    action = "activateTokenIntegration" if activate else "deactivateTokenIntegration"
    name = "activate-token-integration" if activate else "deactivate-token-integration"

    @policies_group.command(name)
    @click.argument("policy_id")
    @click.option("--label", help="Only this entry (default: all entries you may execute it on).")
    @protected_write()
    @pass_state
    def command(state: AppState, policy_id: str, label: str | None) -> None:
        segments = ("entries", label, "actions", action) if label else ("actions", action)
        state.client().post(policy_path(policy_id, *segments))
        output.info(f"{action} done for {policy_id}{'/' + label if label else ''}.")

    command.help = (
        f"{'Add' if activate else 'Remove'} the subject derived from your token "
        f"{'to' if activate else 'from'} the policy's entries (needs EXECUTE permission on the action and a "
        "token-based login; the subject expires with the token)."
    )
    return command


_token_integration(activate=True)
_token_integration(activate=False)

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
"""``dittoctl config``: manage contexts."""

from __future__ import annotations

import sys
from typing import Any

import click
import tomli_w
from rich.console import Console
from rich.table import Table

from dittoctl.auth import provider_for
from dittoctl.cli import output
from dittoctl.cli.options import parse_key_value
from dittoctl.cli.state import AppState, pass_state
from dittoctl.config import AUTH_METHODS, OIDC_FLOWS, AuthConfig, Context
from dittoctl.errors import ConfigError


def complete_context_names(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[str]:
    from dittoctl.config import Config

    try:
        names = Config.load(ctx.find_root().params.get("config_path")).contexts
    except Exception:
        return []
    return [name for name in sorted(names) if name.startswith(incomplete)]


@click.group("config")
def config_group() -> None:
    """Manage contexts: named Ditto endpoints with their authentication settings."""


@config_group.command("add-context")
@click.argument("name")
@click.option("--url", required=True, help="Base URL of Ditto, e.g. https://ditto.example.com")
@click.option(
    "--auth",
    "method",
    type=click.Choice(AUTH_METHODS),
    default="none",
    show_default=True,
    help="How to authenticate; the options below marked [method] configure it.",
)
@click.option("--username", help="[basic] User name.")
@click.option("--subject", help="[preauth] Value of the x-ditto-pre-authenticated header, e.g. nginx:ditto.")
@click.option("--issuer", help="[oidc] Issuer URL used for discovery.")
@click.option("--client-id", help="[oidc] OAuth2 client id.")
@click.option("--flow", type=click.Choice(OIDC_FLOWS), default="pkce", show_default=True, help="[oidc] Login flow.")
@click.option("--scope", "scopes", multiple=True, help="[oidc] Scope to request; repeatable. Default: openid.")
@click.option(
    "--auth-param",
    "auth_params",
    multiple=True,
    metavar="NAME=VALUE",
    help="[oidc] Extra parameter for the authorization request, e.g. audience=ditto. Repeatable.",
)
@click.option(
    "--redirect-port", type=int, default=0, help="[oidc] Fixed loopback port for the PKCE redirect (default: random)."
)
@click.option("--use-id-token", is_flag=True, help="[oidc] Send the id token to Ditto instead of the access token.")
@click.option("--namespace", "namespaces", multiple=True, help="Default namespace for searches. Repeatable.")
@click.option("--header", "headers", multiple=True, metavar="NAME=VALUE", help="Header sent with every request.")
@click.option("--protected", is_flag=True, help="Require typing the context name to confirm writes (e.g. production).")
@click.option("--timeout", type=float, default=30.0, show_default=True, help="Request timeout in seconds.")
@click.option("--ca-cert", type=click.Path(exists=True, dir_okay=False), help="CA bundle to verify TLS with.")
@click.option("--insecure", is_flag=True, help="Don't verify TLS certificates.")
@click.option(
    "--no-search-streaming",
    is_flag=True,
    help="Never stream searches via SSE automatically, e.g. if the Ditto gateway throttles SSE search.",
)
@click.option("--use/--no-use", "use", default=None, help="Make it the current context (default: if it's the first).")
@click.option("--overwrite", is_flag=True, help="Replace an existing context with the same name.")
@pass_state
def add_context(state: AppState, name: str, **opts: Any) -> None:
    """Add a context."""
    config = state.config()
    if name in config.contexts and not opts["overwrite"]:
        raise ConfigError(f"context '{name}' already exists; pass --overwrite to replace it")
    if opts["ca_cert"] and opts["insecure"]:
        raise click.UsageError("--ca-cert and --insecure are mutually exclusive")
    auth = AuthConfig(
        method=opts["method"],
        username=opts["username"],
        subject=opts["subject"],
        issuer=opts["issuer"],
        client_id=opts["client_id"],
        flow=opts["flow"],
        scopes=list(opts["scopes"]) or ["openid"],
        extra_params=parse_key_value(opts["auth_params"], "--auth-param"),
        redirect_port=opts["redirect_port"],
        use_token="id" if opts["use_id_token"] else "access",
    )
    context = Context(
        name=name,
        url=opts["url"].rstrip("/"),
        auth=auth,
        namespaces=list(opts["namespaces"]),
        headers=parse_key_value(opts["headers"], "--header", "=:"),
        protected=opts["protected"],
        timeout=opts["timeout"],
        verify=opts["ca_cert"] or not opts["insecure"],
        search_streaming=not opts["no_search_streaming"],
    )
    config.set_context(context)
    use = opts["use"] if opts["use"] is not None else config.current_context is None
    if use:
        config.current_context = name
    config.save()
    output.info(f"Context '{name}' saved to {config.path}" + (" and selected." if use else "."))
    if auth.method in ("basic", "token", "oidc"):
        output.info("Run 'dittoctl auth login' to store credentials.")


@config_group.command("use-context")
@click.argument("name", shell_complete=complete_context_names)
@pass_state
def use_context(state: AppState, name: str) -> None:
    """Select the context used when --context is not given."""
    config = state.config()
    config.get_context(name)
    config.current_context = name
    config.save()
    output.info(f"Switched to context '{name}'.")


@config_group.command("current-context")
@pass_state
def current_context(state: AppState) -> None:
    """Print the name of the current context."""
    current = state.config().current_context
    if not current:
        raise ConfigError("no current context")
    click.echo(current)


@config_group.command("get-contexts")
@pass_state
def get_contexts(state: AppState) -> None:
    """List all contexts."""
    config = state.config()
    table = Table(box=None, pad_edge=False)
    for column in ("CURRENT", "NAME", "URL", "AUTH", "PROTECTED"):
        table.add_column(column)
    for name, ctx in sorted(config.contexts.items()):
        auth = ctx.auth.method + (f" ({ctx.auth.flow})" if ctx.auth.method == "oidc" else "")
        current = "*" if name == config.current_context else ""
        table.add_row(current, name, ctx.url, auth, "yes" if ctx.protected else "")
    Console(emoji=False, markup=False, file=sys.stdout).print(table)


@config_group.command("view")
@click.argument("name", required=False, shell_complete=complete_context_names)
@pass_state
def view(state: AppState, name: str | None) -> None:
    """Print the configuration, or a single context, as TOML."""
    config = state.config()
    if name:
        click.echo(tomli_w.dumps({"contexts": {name: config.get_context(name).to_toml()}}), nl=False)
        return
    data: dict[str, Any] = {}
    if config.current_context:
        data["current-context"] = config.current_context
    data["contexts"] = {n: c.to_toml() for n, c in sorted(config.contexts.items())}
    click.echo(tomli_w.dumps(data), nl=False)


@config_group.command("delete-context")
@click.argument("name", shell_complete=complete_context_names)
@pass_state
def delete_context(state: AppState, name: str) -> None:
    """Delete a context and its stored credentials."""
    config = state.config()
    context = config.delete_context(name)
    provider_for(context, state.store()).logout()
    config.save()
    output.info(f"Deleted context '{name}'.")


@config_group.command("path")
@pass_state
def path(state: AppState) -> None:
    """Print the path of the config file."""
    click.echo(str(state.config().path))

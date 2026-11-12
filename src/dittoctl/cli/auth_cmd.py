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
"""``dittoctl auth``: log in and out, show the auth status, print tokens."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import click

from dittoctl.cli import output
from dittoctl.cli.options import output_option
from dittoctl.cli.state import AppState, pass_state
from dittoctl.errors import AuthError


def _read_stdin_secret() -> str:
    secret = sys.stdin.read().strip()
    if not secret:
        raise click.UsageError("no secret on stdin")
    return secret


@click.group("auth")
def auth_group() -> None:
    """Log in to the current context and manage its credentials."""


@auth_group.command("login")
@click.option("--password-stdin", is_flag=True, help="[basic] Read the password from stdin.")
@click.option("--token-stdin", is_flag=True, help="[token] Read the bearer token from stdin.")
@click.option("--secret-stdin", is_flag=True, help="[oidc] Read the client secret from stdin.")
@click.option("--no-browser", is_flag=True, help="[oidc pkce] Print the login URL instead of opening a browser.")
@pass_state
def login(state: AppState, password_stdin: bool, token_stdin: bool, secret_stdin: bool, no_browser: bool) -> None:
    """Obtain credentials and store them in the OS keyring.

    \b
    basic   prompts for the password (or reads it with --password-stdin)
    token   prompts for the token (or reads it with --token-stdin)
    oidc    runs the configured flow: browser login (pkce), device code (device),
            or client credentials (with the client secret from --secret-stdin)
    """
    context = state.context()
    method = context.auth.method
    secret = None
    if method == "basic":
        prompt = f"Password for {context.auth.username}"
        secret = _read_stdin_secret() if password_stdin else click.prompt(prompt, hide_input=True)
    elif method == "token":
        secret = _read_stdin_secret() if token_stdin else click.prompt("Bearer token", hide_input=True)
    elif method == "oidc":
        if secret_stdin:
            secret = _read_stdin_secret()
        elif context.auth.flow == "client-credentials" and sys.stdin.isatty():
            secret = click.prompt("Client secret", hide_input=True)
    else:
        output.info(f"Context '{context.name}' uses auth method '{method}', which needs no login.")
        return
    state.auth(context).login(secret=secret, open_browser=not no_browser)
    output.info(f"Logged in to context '{context.name}'.")


@auth_group.command("logout")
@pass_state
def logout(state: AppState) -> None:
    """Delete the stored credentials of the current context."""
    context = state.context()
    state.auth(context).logout()
    output.info(f"Logged out of context '{context.name}'.")


@auth_group.command("status")
@output_option(("text", "json"), "text")
@pass_state
def status(state: AppState, output_format: str) -> None:
    """Show how the current context authenticates and whether credentials are available."""
    context = state.context()
    info = state.auth(context).status()
    info["url"] = context.url
    if output_format == "json":
        output.emit(info)
        return
    for key in ("context", "url", "method", "username", "subject", "issuer", "client_id", "flow"):
        if info.get(key):
            click.echo(f"{key + ':':<15}{info[key]}")
    click.echo(f"{'authenticated:':<15}{'yes' if info.get('authenticated') else 'no'}")
    if expires_at := info.get("expires_at"):
        when = datetime.fromtimestamp(expires_at, UTC).isoformat(timespec="seconds")
        click.echo(f"{'expires:':<15}{when}" + (" (refreshable)" if info.get("refreshable") else ""))
    if claims := info.get("claims"):
        for claim in ("sub", "iss", "aud", "email"):
            if claim in claims:
                click.echo(f"{'token ' + claim + ':':<15}{claims[claim]}")


@auth_group.command("token")
@pass_state
def token(state: AppState) -> None:
    """Print a valid bearer token, for example to paste into the Ditto UI or use with curl."""
    bearer = state.auth().bearer_token()
    if not bearer:
        raise AuthError("the current context does not authenticate with a bearer token")
    click.echo(bearer)

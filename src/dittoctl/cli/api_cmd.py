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
"""``dittoctl api`` (raw authenticated requests) and ``dittoctl whoami``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from dittoctl.cli import output
from dittoctl.cli.options import conditional_options, output_option, parse_key_value, pop_conditions, protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core.client import MERGE_PATCH

METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
READ_METHODS = ("GET", "HEAD", "OPTIONS")


def read_data(value: str) -> str:
    """``@file`` reads a file, ``@-`` reads stdin, anything else is the data itself."""
    if value == "@-":
        return sys.stdin.read()
    if value.startswith("@"):
        try:
            return Path(value[1:]).read_text(encoding="utf-8")
        except OSError as e:
            raise click.BadParameter(str(e), param_hint="--data") from e
    return value


def _content_type(method: str, data: str) -> str:
    try:
        json.loads(data)
    except ValueError:
        return "text/plain"
    return MERGE_PATCH if method == "PATCH" else "application/json"


@click.command("api")
@click.argument("method", type=click.Choice(METHODS, case_sensitive=False), metavar="METHOD")
@click.argument("path")
@click.option("-d", "--data", help="Request body: inline, @file, or @- for stdin.")
@click.option("-q", "--query", "query", multiple=True, metavar="NAME=VALUE", help="Query parameter. Repeatable.")
@click.option("--content-type", help="Content type of the body (default: derived from method and body).")
@click.option("-i", "--include", is_flag=True, help="Print the response status and headers to stderr.")
@output_option(("json", "ndjson", "raw"), "json")
@conditional_options
@protected_write(lambda params: params["method"].upper() not in READ_METHODS)
@pass_state
def api(
    state: AppState,
    method: str,
    path: str,
    data: str | None,
    query: tuple[str, ...],
    content_type: str | None,
    include: bool,
    output_format: str,
    **kwargs: Any,
) -> None:
    """Send an authenticated request to any Ditto endpoint and print the response.

    \b
    Examples:
      dittoctl api GET /api/2/whoami
      dittoctl api GET /api/2/things/org.example:sensor-1 -q fields=thingId,attributes
      dittoctl api PATCH /api/2/things/org.example:sensor-1/attributes -d '{"location":"lab"}' --if-equal skip
      dittoctl api PUT /api/2/things/org.example:sensor-2 -d @thing.json --if-none-match '*'
    """
    conditions = pop_conditions(kwargs)
    method = method.upper()
    if not path.startswith("/"):
        path = "/" + path
    body = read_data(data) if data is not None else None
    response = state.client().request(
        method,
        path,
        params=parse_key_value(query, "--query"),
        content=body,
        content_type=content_type or (_content_type(method, body) if body is not None else None),
        conditions=conditions,
    )
    if include:
        output.info(f"{response.status}")
        for name, value in response.headers.items():
            output.info(f"{name}: {value}")
    if response.body is not None:
        output.emit(response.body, output_format, text="json" not in response.headers.get("content-type", ""))


@click.command("whoami")
@output_option(("json", "text"), "text")
@pass_state
def whoami(state: AppState, output_format: str) -> None:
    """Show the subjects Ditto derives from your credentials."""
    info = state.client().whoami()
    if output_format == "json" or not isinstance(info, dict):
        output.emit(info)
        return
    default = info.get("defaultSubject")
    for subject in info.get("subjects", []):
        marker = " (default)" if subject == default else ""
        click.echo(f"{subject}{marker}")

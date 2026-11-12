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
"""``dittoctl rql``: check and format RQL filters offline."""

from __future__ import annotations

import click

from dittoctl.cli import output
from dittoctl.cli.api_cmd import read_data
from dittoctl.core import rql
from dittoctl.errors import CheckFailedError, DittoctlError


def _parse(expression: str, error: type[DittoctlError] = DittoctlError) -> rql.Node:
    try:
        return rql.parse(read_data(expression))
    except rql.RqlError as e:
        raise error("invalid RQL: " + e.render()) from None


@click.group("rql")
def rql_group() -> None:
    """Check and format RQL filter expressions, without contacting Ditto."""


@rql_group.command("lint")
@click.argument("expression", metavar="EXPRESSION|@FILE|@-")
def lint(expression: str) -> None:
    """Check an RQL filter; on error, show where it is. Exit code 6 if invalid."""
    node = _parse(expression, CheckFailedError)
    for warning in rql.warnings(node):
        output.warn(warning)
    output.info("valid")


@rql_group.command("fmt")
@click.argument("expression", metavar="EXPRESSION|@FILE|@-")
@click.option("--compact", is_flag=True, help="Single line without whitespace (the form sent to Ditto).")
def fmt(expression: str, compact: bool) -> None:
    """Pretty-print an RQL filter, one condition per line."""
    node = _parse(expression)
    click.echo(rql.compact(node) if compact else rql.pretty(node))

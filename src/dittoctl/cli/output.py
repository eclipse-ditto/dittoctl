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
"""Terminal output. Data goes to stdout, everything else (progress, hints, errors) to stderr."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click
from rich.console import Console
from rich.markup import escape

from dittoctl.errors import DittoctlError, DittoError
from dittoctl.formats import json_writer

DATA_FORMATS = ("json", "ndjson", "raw")
# set by AI coding agents in the environment of the commands they run (Claude Code sets both)
AGENT_ENV_VARS = ("CLAUDECODE", "AI_AGENT")
COMPACT = (",", ":")
# in agent mode, results on stdout are limited to this many items unless --limit or --all is given
AGENT_LIMIT = 50
# and streams (watch, follow) stop after this many seconds unless --duration is given
AGENT_DURATION = 30.0

_agent = False


def detect_agent() -> bool:
    """Whether dittoctl runs under an AI agent, judging by the environment."""
    return any(os.environ.get(name, "") not in ("", "0", "false") for name in AGENT_ENV_VARS)


def set_agent_mode(enabled: bool | None) -> None:
    """Agent mode: compact JSON, errors as JSON, bounded output. ``None`` detects it from the environment."""
    global _agent
    _agent = detect_agent() if enabled is None else enabled


def agent_mode() -> bool:
    return _agent


def agent_limit(limit: int | None, all_items: bool, *, to_file: bool = False) -> int | None:
    """The limit agents get when they set none, so that a result doesn't flood their context."""
    return AGENT_LIMIT if _agent and limit is None and not all_items and not to_file else None


def agent_duration(duration: float | None, max_items: int | None = None) -> float | None:
    """The duration of a stream: --duration (0 = unlimited), else in agent mode a default."""
    if duration is not None:
        return duration or None
    return AGENT_DURATION if _agent and max_items is None else None


def more_results(what: str, limit: int, hint: str) -> None:
    info(f"Showing the first {limit} {what}; there are more (agent mode limits output). {hint}")


def dumps(data: Any) -> str:
    """One line of JSON, as written to NDJSON output."""
    return json.dumps(data, ensure_ascii=False, separators=COMPACT)


def line(data: Any) -> None:
    """Write one NDJSON line to stdout (highlighted on a terminal)."""
    json_writer(sys.stdout)(dumps(data) + "\n")
    sys.stdout.flush()


def _stdout() -> Console:
    # created per call so that click's CliRunner (which swaps sys.stdout) captures the output
    return Console(emoji=False, file=sys.stdout, soft_wrap=True)


def _stderr() -> Console:
    return Console(emoji=False, file=sys.stderr, soft_wrap=True)


def info(message: str) -> None:
    _stderr().print(escape(message), highlight=False)


def debug(message: str) -> None:
    _stderr().print(escape(message), style="dim", highlight=False)


def warn(message: str) -> None:
    _stderr().print(f"[yellow]Warning:[/] {escape(message)}", highlight=False)


def emit(data: Any, fmt: str = "json", *, text: bool = False) -> None:
    """Write data to stdout: pretty JSON on a terminal, indented JSON when piped (single-line for agents).

    ``text`` marks data that is plain text (a non-JSON response body), which is written as is.
    """
    if text or fmt == "raw":
        click.echo(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
    elif fmt == "ndjson":
        items = data if isinstance(data, list) else [data]
        for item in items:
            line(item)
    elif sys.stdout.isatty():
        _stdout().print_json(data=data)
    elif _agent:
        click.echo(dumps(data))
    else:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))


def error_json(exit_code: int, message: str, **fields: Any) -> None:
    """An error as one line of JSON on stderr, for agents: ``{"exitCode": 4, "message": ..., ...}``."""
    body = {"exitCode": int(exit_code), "message": message, **{k: v for k, v in fields.items() if v is not None}}
    click.echo(dumps(body), err=True)


def error(exc: DittoctlError) -> None:
    if _agent:
        if isinstance(exc, DittoError):
            error_json(
                exc.exit_code,
                exc.message or str(exc),
                status=exc.status,
                error=exc.error,
                description=exc.description,
                href=exc.href,
                correlationId=exc.correlation_id,
            )
        else:
            error_json(exc.exit_code, str(exc))
        return
    console = _stderr()
    console.print(f"[bold red]Error:[/] {escape(str(exc))}", highlight=False)
    if isinstance(exc, DittoError):
        if exc.description:
            console.print(f"  {escape(exc.description)}", highlight=False)
        if exc.href:
            console.print(f"  See {escape(exc.href)}", style="dim", highlight=False)
        if exc.correlation_id:
            console.print(f"  correlation-id: {escape(exc.correlation_id)}", style="dim", highlight=False)

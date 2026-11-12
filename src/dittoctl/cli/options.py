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
"""Reusable click options."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import click

from dittoctl.cli.state import AppState
from dittoctl.core.conditions import Conditions, IfEqual, LiveTimeoutStrategy
from dittoctl.core.devops import duration_seconds
from dittoctl.errors import DittoctlError

F = TypeVar("F", bound=Callable[..., Any])

_CONDITION_KEYS = (
    "if_match",
    "if_none_match",
    "if_equal",
    "condition",
    "patch_conditions",
    "live_condition",
    "live_timeout_strategy",
)


def parse_key_value(values: tuple[str, ...], option: str, separators: str = "=") -> dict[str, str]:
    """Parse repeated NAME=VALUE options. The first matching separator splits name and value."""
    result: dict[str, str] = {}
    for item in values:
        positions = [i for i in (item.find(s) for s in separators) if i > 0]
        if not positions:
            raise click.BadParameter(f"expected NAME{separators[0]}VALUE, got '{item}'", param_hint=option)
        i = min(positions)
        result[item[:i].strip()] = item[i + 1 :].strip()
    return result


def conditional_options(f: F) -> F:
    """Add Ditto's conditional request options (see PLAN.md 4.8) to a command."""
    options = [
        click.option(
            "--if-match",
            metavar="ETAG|*",
            help="Only apply if the entity has this ETag (e.g. rev:5); '*' requires that it exists.",
        ),
        click.option(
            "--if-none-match",
            metavar="ETAG|*",
            help="'*' only creates and never overwrites; with an ETag on reads, Ditto answers 304 if unchanged.",
        ),
        click.option(
            "--if-equal",
            type=click.Choice([v.value for v in IfEqual]),
            help="What Ditto does if the new value equals the current one; 'skip' avoids no-op events.",
        ),
        click.option("--condition", metavar="RQL", help="Only apply if the entity matches this RQL condition."),
        click.option(
            "--patch-condition",
            "patch_conditions",
            multiple=True,
            metavar="PATH=RQL",
            help="Per-path condition for merge requests (Ditto 3.8+). Repeatable.",
        ),
        click.option("--live-condition", metavar="RQL", help="Route retrieves to the live channel if this matches."),
        click.option(
            "--live-timeout-strategy",
            type=click.Choice([v.value for v in LiveTimeoutStrategy]),
            help="What to do if the device doesn't answer a live request in time.",
        ),
    ]
    for option in reversed(options):
        f = option(f)
    return f


def pop_conditions(kwargs: dict[str, Any]) -> Conditions:
    """Remove the conditional options from a command's kwargs and build Conditions from them."""
    values = {key: kwargs.pop(key, None) for key in _CONDITION_KEYS}
    return Conditions(
        if_match=values["if_match"],
        if_none_match=values["if_none_match"],
        if_equal=IfEqual(values["if_equal"]) if values["if_equal"] else None,
        condition=values["condition"],
        patch_conditions=parse_key_value(values["patch_conditions"] or (), "--patch-condition"),
        live_condition=values["live_condition"],
        live_timeout_strategy=(
            LiveTimeoutStrategy(values["live_timeout_strategy"]) if values["live_timeout_strategy"] else None
        ),
    )


def output_option(formats: tuple[str, ...], default: str) -> Callable[[F], F]:
    return click.option(
        "-o",
        "--output",
        "output_format",
        type=click.Choice(formats),
        default=default,
        show_default=True,
        help="Output format.",
    )


def confirm_context_option(f: F) -> F:
    return click.option(
        "--confirm-context",
        metavar="NAME",
        help="Confirm a protected context without the prompt (for scripts).",
    )(f)


def protected_write(when: Callable[[Mapping[str, Any]], bool] | None = None) -> Callable[[F], F]:
    """Adds --confirm-context; before the command runs, a protected context has to be confirmed.

    ``when`` decides from the command's arguments whether this invocation writes at all (e.g. ``api GET``
    doesn't). Put the decorator directly above ``@pass_state``.
    """

    def decorator(f: F) -> F:
        @functools.wraps(f)
        def wrapper(*args: Any, confirm_context: str | None = None, **kwargs: Any) -> Any:
            ctx = click.get_current_context()
            if when is None or when(ctx.params):
                state = ctx.find_object(AppState)
                assert state is not None
                state.confirm_protected(f"run '{ctx.command_path}'", confirm_context)
            return f(*args, **kwargs)

        return confirm_context_option(wrapper)  # type: ignore[return-value]

    return decorator


class Duration(click.ParamType):
    """``30s``, ``2m``, ``500ms``, or plain seconds; converted to seconds."""

    name = "DURATION"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> float:
        if isinstance(value, float | int):
            return float(value)
        try:
            return duration_seconds(value)
        except DittoctlError as e:
            self.fail(str(e), param, ctx)


def all_option(f: F) -> F:
    return click.option(
        "--all",
        "all_items",
        is_flag=True,
        help="Don't limit the output (agent mode shows the first 50 by default).",
    )(f)


def duration_option(what: str) -> Callable[[F], F]:
    return click.option(
        "--duration",
        type=Duration(),
        help=f"Stop {what} after this long, e.g. 30s or 5m; 0 never stops (default; agent mode: 30s).",
    )

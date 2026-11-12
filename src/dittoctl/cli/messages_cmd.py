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
"""``dittoctl messages``: send messages to things and features."""

from __future__ import annotations

import json
import threading
from typing import Any

import click

from dittoctl.cli import output
from dittoctl.cli.api_cmd import read_data
from dittoctl.cli.bulk_options import (
    WriteOptions,
    confirm,
    execute,
    pop_selection,
    select,
    selector_options,
    write_options,
)
from dittoctl.cli.options import protected_write
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core.bulk import Category, Outcome
from dittoctl.core.things import thing_path
from dittoctl.core.writes import message_operation


@click.group("messages")
def messages_group() -> None:
    """Send messages to things and their features, for example commands for devices."""


@messages_group.command("send")
@click.argument("subject")
@click.argument("thing_ids", nargs=-1, metavar="[THING_ID]...")
@click.option("-d", "--data", metavar="JSON|TEXT|@FILE|@-", help="Message payload; JSON if it parses, else text.")
@click.option("--content-type", help="Content type of the payload (default: application/json, or text/plain).")
@click.option("--feature", help="Send to this feature of each thing instead of the thing itself.")
@click.option("--outbox", is_flag=True, help="Send from the thing (outbox) instead of to it (inbox).")
@click.option(
    "--timeout",
    type=click.IntRange(0, 60),
    default=10,
    show_default=True,
    help="Seconds to wait for each response; 0 sends without waiting (fire and forget).",
)
@click.option(
    "--paginate",
    metavar="RESPONSE_FIELD[:REQUEST_FIELD]",
    help="Follow paged answers: re-send while the response contains RESPONSE_FIELD, passing its value as "
    "REQUEST_FIELD (default: the same name) in the payload.",
)
@click.option(
    "--max-pages",
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Upper limit of pages per thing with --paginate.",
)
@selector_options
@write_options
@pass_state
def send(
    state: AppState,
    subject: str,
    thing_ids: tuple[str, ...],
    data: str | None,
    content_type: str | None,
    feature: str | None,
    outbox: bool,
    timeout: int,
    paginate: str | None,
    max_pages: int,
    **kwargs: Any,
) -> None:
    """Send the message SUBJECT to each selected thing and print the responses as NDJSON.

    Each response line has thingId, result, status and response; with --results, failed things get a line too.

    Messages are not retried automatically, as devices may not handle duplicates.

    \b
    Examples:
      dittoctl messages send reboot org.example:sensor-1 --timeout 0
      dittoctl messages send set-interval -d '{"seconds":60}' --feature config -f 'eq(attributes/model,"X1")'
    """
    options = WriteOptions.pop(kwargs)
    selection = pop_selection(state, thing_ids, kwargs)
    if selection.ids_file == "-" and data == "@-":
        raise click.UsageError("stdin can't provide both the thing ids (--ids-file -) and the data (@-)")
    body: Any = None
    if data is not None:
        text = read_data(data)
        try:
            body = json.loads(text)
        except ValueError:
            body = text
            content_type = content_type or "text/plain"
    ids = select(state, selection)
    confirm(state, len(ids), options, f"send '{subject}' to")
    lock = threading.Lock()

    pagination = None
    if paginate:
        response_field, _, request_field = paginate.partition(":")
        pagination = (response_field, request_field or response_field)
        if timeout == 0:
            raise click.UsageError("--paginate needs responses, so --timeout must not be 0")

    def print_response(outcome: Outcome) -> None:
        if timeout == 0 or outcome.detail is None or outcome.category == Category.PLANNED:
            return
        pages = outcome.detail if pagination else [outcome.detail]
        with lock:
            for number, page in enumerate(pages, 1):
                line: dict[str, Any] = {
                    "thingId": outcome.thing_id,
                    "result": str(outcome.category),
                    "status": outcome.status,
                    "response": page,
                }
                if pagination:
                    line["page"] = number
                output.line(line)

    operation = message_operation(
        state.client(),
        subject,
        body,
        feature=feature,
        outbox=outbox,
        timeout=timeout,
        content_type=content_type,
        paginate=pagination,
        max_pages=max_pages,
        dry_run=options.dry_run,
    )
    execute(
        state, ids, operation, options, f"send '{subject}'", on_outcome=print_response, reports_successes=timeout != 0
    )


@messages_group.command("claim")
@click.argument("thing_id")
@click.option(
    "--timeout",
    type=click.IntRange(0, 60),
    default=10,
    show_default=True,
    help="Seconds to wait for the device's answer.",
)
@protected_write()
@pass_state
def claim(state: AppState, thing_id: str, timeout: int) -> None:
    """Claim a thing: send a claim message to its inbox, which the device (or a connected service) answers,
    for example by granting you access in the thing's policy."""
    response = state.client().post(thing_path(thing_id, "inbox/claim"), params={"timeout": str(timeout)}, json={})
    if response.body is not None:
        output.emit(response.body)
    else:
        output.info(f"Claim sent to {thing_id} ({response.status}).")

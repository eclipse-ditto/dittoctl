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
"""Minimal server-sent events parser (https://html.spec.whatwg.org/multipage/server-sent-events.html)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SseEvent:
    data: str
    event: str | None = None
    id: str | None = None


def iter_sse(lines: Iterable[str]) -> Iterator[SseEvent]:
    """Group the lines of an event stream into events. Comment lines (``:``) are keep-alives and skipped."""
    data: list[str] = []
    event: str | None = None
    event_id: str | None = None
    for line in lines:
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield SseEvent("\n".join(data), event, event_id)
            data, event = [], None
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if name == "data":
            data.append(value)
        elif name == "event":
            event = value
        elif name == "id":
            event_id = value
    if data:
        yield SseEvent("\n".join(data), event, event_id)

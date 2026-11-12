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
"""Bounding results and streams: at most N items, or only for a while."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


class Limited(Generic[T]):
    """The first ``limit`` items of an iterable; afterwards, ``more`` tells whether there were more.

    The source is read one item further than ``limit`` to find out.
    """

    def __init__(self, items: Iterable[T], limit: int) -> None:
        self._items = items
        self.limit = limit
        self.more = False

    def __iter__(self) -> Iterator[T]:
        source = iter(self._items)
        try:
            for count, item in enumerate(source):
                if count == self.limit:
                    self.more = True
                    return
                yield item
        finally:
            _close(source)


def _close(source: Iterator[object]) -> None:
    """Close a generator that wasn't read to the end, e.g. to end its HTTP stream now rather than at exit."""
    close = getattr(source, "close", None)
    if close:
        close()


@dataclass
class _Failure:
    error: BaseException


_DONE = object()


class Timeboxed(Generic[T]):
    """Items of a blocking iterable (e.g. an SSE stream) until ``duration`` seconds passed or ``max_items`` arrived.

    The source is read in a background thread, so that waiting for the next item can't outlast the duration.
    Afterwards, ``stopped`` is ``"duration"``, ``"max-items"``, or ``None`` if the source ended by itself.
    Errors of the source are raised by the iteration.
    """

    def __init__(self, items: Iterable[T], *, duration: float | None = None, max_items: int | None = None) -> None:
        self._items = items
        self.duration = duration
        self.max_items = max_items
        self.stopped: str | None = None

    def __iter__(self) -> Iterator[T]:
        if self.duration is None and self.max_items is None:
            yield from self._items
            return
        if self.duration is None:
            yield from self._first_items()
            return
        received: queue.Queue[object] = queue.Queue()

        def pump() -> None:
            try:
                for item in self._items:
                    received.put(item)
                received.put(_DONE)
            except BaseException as e:
                received.put(_Failure(e))

        threading.Thread(target=pump, daemon=True, name="dittoctl-stream").start()
        deadline = time.monotonic() + self.duration
        count = 0
        while self.max_items is None or count < self.max_items:
            try:
                item = received.get(timeout=max(deadline - time.monotonic(), 0))
            except queue.Empty:
                self.stopped = "duration"
                return
            if item is _DONE:
                return
            if isinstance(item, _Failure):
                raise item.error
            count += 1
            yield item  # type: ignore[misc]
        self.stopped = "max-items"

    def _first_items(self) -> Iterator[T]:
        assert self.max_items is not None
        source = iter(self._items)
        try:
            for count, item in enumerate(source, 1):
                yield item
                if count == self.max_items:
                    self.stopped = "max-items"
                    return
        finally:
            _close(source)

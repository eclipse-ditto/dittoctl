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
"""The bulk engine: run one operation per thing, concurrently, rate-limited, journaled and resumable."""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

from dittoctl.errors import DittoctlError, DittoError


class Category(StrEnum):
    OK = "ok"
    # Ditto skipped the write because the value didn't change (If-Equal: skip), or nothing needed to change
    UNCHANGED = "unchanged"
    # the request's --condition didn't match
    CONDITION_NOT_MET = "condition-not-met"
    # create-only (If-None-Match: *) on a thing that already exists
    EXISTS = "exists"
    # If-Match didn't match, also after re-reading (concurrent modification)
    CONFLICT = "conflict"
    NOT_FOUND = "not-found"
    FAILED = "failed"
    # dry run: what would be sent
    PLANNED = "planned"


FAILURES = frozenset({Category.CONFLICT, Category.NOT_FOUND, Category.FAILED})


@dataclass
class Outcome:
    thing_id: str
    category: Category
    status: int | None = None
    error: str | None = None
    message: str | None = None
    # dry run: the planned request; messages: the response
    detail: Any = None
    # Ditto's explanation of an error, e.g. which fields don't conform to the thing's WoT model
    description: str | None = None

    @property
    def failed(self) -> bool:
        return self.category in FAILURES


def is_unchanged(exc: DittoError) -> bool:
    """Ditto answers If-Equal: skip with 412 like a failed If-Match; only the message tells them apart."""
    return exc.status == 412 and "previous value was equal" in (exc.message or "")


def classify(thing_id: str, exc: Exception) -> Outcome:
    """Map an error of one thing's operation to an outcome."""
    if isinstance(exc, DittoError):
        if exc.status == 412:
            if exc.condition_failed:
                category = Category.CONDITION_NOT_MET
            elif is_unchanged(exc):
                category = Category.UNCHANGED
            else:
                category = Category.CONFLICT
        else:
            category = Category.NOT_FOUND if exc.status == 404 else Category.FAILED
        return Outcome(thing_id, category, exc.status, exc.error, exc.message, description=exc.description)
    if isinstance(exc, DittoctlError):
        return Outcome(thing_id, Category.FAILED, None, "dittoctl", str(exc))
    return Outcome(thing_id, Category.FAILED, None, type(exc).__name__, str(exc))


class RateLimiter:
    """Spaces calls evenly to at most ``rate`` per second, across threads."""

    def __init__(
        self, rate: float, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        if rate <= 0:
            raise DittoctlError("--rate must be greater than 0")
        self.interval = 1.0 / rate
        self.clock = clock
        self.sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self.clock()
            slot = max(now, self._next)
            self._next = slot + self.interval
        if slot > now:
            self.sleep(slot - now)


class Journal:
    """Append-only record of finished things (``id<TAB>category``) so that an interrupted run can be resumed.

    Failed things are not recorded: a resumed run tries them again.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._file: TextIO | None = None

    def completed(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open(encoding="utf-8") as f:
            return {line.split("\t", 1)[0] for line in f if line.strip() and not line.startswith("#")}

    def record(self, outcome: Outcome) -> None:
        if outcome.failed or outcome.category == Category.PLANNED:
            return
        with self._lock:
            if self._file is None:
                self._file = self.path.open("a", encoding="utf-8")
            self._file.write(f"{outcome.thing_id}\t{outcome.category}\n")
            self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()


class FailureLog:
    """Writes failed things as ``id<TAB>status<TAB>error<TAB>message<TAB>description``.

    The file can be used as ``--ids-file``.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._file: TextIO | None = None

    def record(self, outcome: Outcome) -> None:
        if not outcome.failed:
            return
        message, description = (
            (text or "").replace("\t", " ").replace("\n", " ") for text in (outcome.message, outcome.description)
        )
        with self._lock:
            if self._file is None:
                self._file = self.path.open("w", encoding="utf-8")
                self._file.write("# thingId\tstatus\terror\tmessage\tdescription\n")
            self._file.write(
                f"{outcome.thing_id}\t{outcome.status or ''}\t{outcome.error or ''}\t{message}\t{description}\n"
            )
            self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()


@dataclass
class Summary:
    total: int
    counts: Counter[Category] = field(default_factory=Counter)
    skipped_by_journal: int = 0
    elapsed: float = 0.0
    interrupted: bool = False

    @property
    def processed(self) -> int:
        return sum(self.counts.values())

    @property
    def failures(self) -> int:
        return sum(n for category, n in self.counts.items() if category in FAILURES)

    def describe(self, noun: str = "things") -> str:
        parts = [f"{category} {n}" for category, n in sorted(self.counts.items(), key=lambda kv: -kv[1])]
        if self.skipped_by_journal:
            parts.append(f"already done (journal) {self.skipped_by_journal}")
        rate = f" ({self.processed / self.elapsed:.0f}/s)" if self.elapsed > 0 and self.processed else ""
        return f"{self.processed} of {self.total} {noun} in {self.elapsed:.1f}s{rate}: " + (", ".join(parts) or "none")


def run_bulk(
    thing_ids: Sequence[str],
    operation: Callable[[str], Outcome],
    *,
    concurrency: int = 8,
    rate: float | None = None,
    journal: Journal | None = None,
    resume: bool = False,
    failure_log: FailureLog | None = None,
    on_outcome: Callable[[Outcome], None] | None = None,
) -> Summary:
    """Run ``operation`` for each thing id with up to ``concurrency`` in flight.

    Errors raised by an operation are classified per thing and never stop the run. Ctrl+C stops submitting new
    things, waits for the ones in flight and returns a summary with ``interrupted`` set; with a journal, the
    run can then be resumed.
    """
    if concurrency < 1:
        raise DittoctlError("--concurrency must be at least 1")
    done_before = journal.completed() if journal and resume else set()
    pending: Iterable[str] = [i for i in thing_ids if i not in done_before]
    summary = Summary(total=len(thing_ids), skipped_by_journal=len(thing_ids) - len(pending))
    limiter = RateLimiter(rate) if rate else None
    started = time.monotonic()

    def task(thing_id: str) -> Outcome:
        if limiter:
            limiter.acquire()
        try:
            return operation(thing_id)
        except Exception as e:
            return classify(thing_id, e)

    def finish(future: Future[Outcome]) -> None:
        outcome = future.result()
        summary.counts[outcome.category] += 1
        if journal:
            journal.record(outcome)
        if failure_log:
            failure_log.record(outcome)
        if on_outcome:
            on_outcome(outcome)

    executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="dittoctl-bulk")
    in_flight: set[Future[Outcome]] = set()
    try:
        for thing_id in pending:
            while len(in_flight) >= concurrency * 2:
                done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    finish(future)
            in_flight.add(executor.submit(task, thing_id))
        while in_flight:
            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                finish(future)
    except KeyboardInterrupt:
        summary.interrupted = True
        for future in in_flight:
            future.cancel()
        for future in in_flight:
            if not future.cancelled():
                finish(future)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        summary.elapsed = time.monotonic() - started
        if journal:
            journal.close()
        if failure_log:
            failure_log.close()
    return summary

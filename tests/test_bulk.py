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
import threading

import pytest

from dittoctl.core.bulk import Category, FailureLog, Journal, Outcome, RateLimiter, classify, run_bulk
from dittoctl.core.selectors import read_ids
from dittoctl.errors import DittoctlError, DittoError

SKIPPED = "The previous value was equal to the new value and the 'if-equal' header was set to 'skip'."


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (DittoError(412, "things:precondition.failed", SKIPPED), Category.UNCHANGED),
        (
            DittoError(412, "things:condition.failed", "The specified condition does not match"),
            Category.CONDITION_NOT_MET,
        ),
        (DittoError(412, "policies:condition.failed", "no match"), Category.CONDITION_NOT_MET),
        (DittoError(412, "things:precondition.failed", "if-match evaluated to false"), Category.CONFLICT),
        (DittoError(404, "things:thing.notfound", "not found"), Category.NOT_FOUND),
        (DittoError(500, "internal.error", "boom"), Category.FAILED),
        (DittoctlError("GET failed: connection refused"), Category.FAILED),
        (ValueError("bad"), Category.FAILED),
    ],
)
def test_classify(error, category):
    outcome = classify("a:1", error)
    assert outcome.category == category
    assert outcome.failed is (category in (Category.CONFLICT, Category.NOT_FOUND, Category.FAILED))


def test_run_bulk_counts_and_never_stops_on_errors():
    def operation(thing_id):
        if thing_id.endswith("3"):
            raise DittoError(500, "internal.error", "boom")
        if thing_id.endswith("4"):
            raise DittoError(412, "things:precondition.failed", SKIPPED)
        return Outcome(thing_id, Category.OK, 204)

    ids = [f"a:{i}" for i in range(10)]
    seen = []
    summary = run_bulk(ids, operation, concurrency=3, on_outcome=lambda o: seen.append(o.thing_id))
    assert summary.counts == {Category.OK: 8, Category.FAILED: 1, Category.UNCHANGED: 1}
    assert summary.failures == 1
    assert sorted(seen) == sorted(ids)
    assert "8" in summary.describe()


def test_run_bulk_respects_concurrency():
    running = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def operation(thing_id):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        release.wait(0.01)
        with lock:
            running -= 1
        return Outcome(thing_id, Category.OK)

    run_bulk([f"a:{i}" for i in range(40)], operation, concurrency=4)
    assert peak <= 4


def test_journal_and_resume(tmp_path):
    journal_path = tmp_path / "journal.tsv"
    calls = []

    def operation(thing_id):
        calls.append(thing_id)
        if thing_id == "a:2":
            raise DittoError(500, "internal.error", "boom")
        return Outcome(thing_id, Category.OK)

    ids = ["a:1", "a:2", "a:3"]
    run_bulk(ids, operation, journal=Journal(journal_path))
    # failed things are not journaled, so a resumed run retries them
    assert sorted(line.split("\t")[0] for line in journal_path.read_text().splitlines()) == ["a:1", "a:3"]

    calls.clear()
    summary = run_bulk(ids, operation, journal=Journal(journal_path), resume=True)
    assert calls == ["a:2"]
    assert summary.skipped_by_journal == 2


def test_failure_log_can_be_read_back_as_ids(tmp_path):
    log_path = tmp_path / "failed.tsv"

    def operation(thing_id):
        raise DittoError(404, "things:thing.notfound", "The Thing\twith ID\ncould not be found")

    run_bulk(["a:1", "a:2"], operation, failure_log=FailureLog(log_path))
    text = log_path.read_text()
    assert text.startswith("# thingId\tstatus\terror\tmessage\tdescription\n")
    assert "\ta:" not in text.split("\n", 1)[1]  # tabs/newlines in messages are flattened
    assert sorted(read_ids(text.splitlines())) == ["a:1", "a:2"]


def test_interrupt_finishes_in_flight_and_reports(tmp_path):
    def operation(thing_id):
        return Outcome(thing_id, Category.OK)

    def interrupt_after_first(outcome):
        raise KeyboardInterrupt

    summary = run_bulk([f"a:{i}" for i in range(100)], operation, concurrency=2, on_outcome=interrupt_after_first)
    assert summary.interrupted
    assert summary.processed < 100


def test_rate_limiter_spaces_calls():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(round(seconds, 6))
        now[0] += seconds

    limiter = RateLimiter(4, clock=lambda: now[0], sleep=sleep)
    for _ in range(4):
        limiter.acquire()
    assert sleeps == [0.25, 0.25, 0.25]


def test_rate_must_be_positive():
    with pytest.raises(DittoctlError):
        RateLimiter(0)

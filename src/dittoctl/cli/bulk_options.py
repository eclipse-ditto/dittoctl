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
"""Options and flow shared by commands that act on many things: selection, safety checks, bulk execution."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import click
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from dittoctl.cli import output
from dittoctl.cli.api_cmd import read_data
from dittoctl.cli.options import confirm_context_option
from dittoctl.cli.state import AppState
from dittoctl.cli.things_cmd import resolve_filter, resolve_namespaces
from dittoctl.core.bulk import Category, FailureLog, Journal, Outcome, Summary, run_bulk
from dittoctl.core.selectors import Selection, resolve
from dittoctl.errors import AbortedError, DittoctlError, ExitCode, InterruptedRunError

F = TypeVar("F", bound=Callable[..., Any])
DRY_RUN_SAMPLES = 3
# failed things whose error is shown directly; all of them go to --failed-out
FAILURE_SAMPLES = 3
RESULTS = ("none", "failures", "all")


class BulkFailure(DittoctlError):
    exit_code = ExitCode.PARTIAL_FAILURE


def _apply(f: F, options: list[Callable[[F], F]]) -> F:
    for option in reversed(options):
        f = option(f)
    return f


def selector_options(f: F) -> F:
    """--ids-file, --filter, --namespaces, --include-file, --exclude-file. Thing ids come as arguments."""
    return _apply(
        f,
        [
            click.option("--ids-file", metavar="FILE", help="Thing ids, one per line (first column); - reads stdin."),
            click.option("-f", "--filter", "rql_filter", metavar="RQL", help="Select by RQL filter; @file reads it."),
            click.option("--no-validate", is_flag=True, help="Send the filter without checking it locally first."),
            click.option("-n", "--namespaces", multiple=True, metavar="NS[,NS]", help="Namespaces for --filter."),
            click.option("--include-file", metavar="FILE", help="Only things whose id is also in this file."),
            click.option("--exclude-file", metavar="FILE", help="Leave out things whose id is in this file."),
        ],
    )


def write_options(f: F) -> F:
    """Safety (--dry-run, --yes, --max-affected, --confirm-context) and bulk (--concurrency, --rate, ...)."""
    return _apply(
        f,
        [
            click.option("--dry-run", is_flag=True, help="Show what would be sent, without writing anything."),
            click.option("-y", "--yes", is_flag=True, help="Don't ask; required above --max-affected things."),
            click.option(
                "--max-affected",
                type=click.IntRange(min=0),
                default=100,
                show_default=True,
                help="Above this many things, --yes is required.",
            ),
            confirm_context_option,
            click.option(
                "--concurrency",
                type=click.IntRange(1, 64),
                default=8,
                show_default=True,
                help="Requests in flight at the same time.",
            ),
            click.option("--rate", type=float, metavar="N", help="At most N requests per second."),
            click.option("--journal", metavar="FILE", help="Record finished things here, to --resume later."),
            click.option("--resume", is_flag=True, help="Skip the things already recorded in --journal."),
            click.option(
                "--failed-out", metavar="FILE", help="Write failed things here (usable as --ids-file to retry them)."
            ),
            click.option(
                "--results",
                type=click.Choice(RESULTS),
                help="Print a JSON line per thing on stdout: 'failures' (with Ditto's error and its description; "
                "in a dry run, the first planned requests) or 'all', then a summary line. "
                "Default: none; agent mode: failures.",
            ),
        ],
    )


@dataclass
class WriteOptions:
    dry_run: bool
    yes: bool
    max_affected: int
    confirm_context: str | None
    concurrency: int
    rate: float | None
    journal: str | None
    resume: bool
    failed_out: str | None
    results: str | None

    @classmethod
    def pop(cls, kwargs: dict[str, Any]) -> WriteOptions:
        options = cls(**{name: kwargs.pop(name) for name in cls.__dataclass_fields__})
        if options.resume and not options.journal:
            raise click.UsageError("--resume needs --journal FILE")
        if options.results is None:
            options.results = "failures" if output.agent_mode() else "none"
        return options


def pop_selection(state: AppState, thing_ids: tuple[str, ...], kwargs: dict[str, Any]) -> Selection:
    rql_filter = kwargs.pop("rql_filter")
    no_validate = kwargs.pop("no_validate")
    namespaces = kwargs.pop("namespaces")
    return Selection(
        ids=list(thing_ids),
        ids_file=kwargs.pop("ids_file"),
        rql_filter=resolve_filter(rql_filter, not no_validate),
        namespaces=resolve_namespaces(state, namespaces) if rql_filter else [],
        include_file=kwargs.pop("include_file"),
        exclude_file=kwargs.pop("exclude_file"),
    )


def select(state: AppState, selection: Selection) -> list[str]:
    ids = resolve(state.client(), selection, streaming_allowed=state.context().search_streaming, warn=output.warn)
    output.info(f"Selected {len(ids)} thing(s).")
    return ids


def read_json(value: str, option: str = "--data") -> Any:
    text = read_data(value)
    try:
        return json.loads(text)
    except ValueError as e:
        raise click.BadParameter(f"not valid JSON: {e}", param_hint=option) from None


def confirm(state: AppState, count: int, options: WriteOptions, action: str, *, destructive: bool = False) -> None:
    """Ask for the confirmations the safety rules require; raises AbortedError if they aren't given."""
    if options.dry_run or count == 0:
        return
    interactive = sys.stdin.isatty()
    if count > options.max_affected and not options.yes:
        raise AbortedError(
            f"this would {action} {count} things, more than --max-affected {options.max_affected}. "
            "Check the selection with --dry-run, then pass --yes (or raise --max-affected)"
        )
    if destructive and not options.yes:
        if not interactive:
            raise AbortedError(f"refusing to {action} {count} thing(s) without --yes when not interactive")
        if not click.confirm(f"{action.capitalize()} {count} thing(s)? This cannot be undone", default=False):
            raise AbortedError("not confirmed")
    state.confirm_protected(f"{action} {count} thing(s)", options.confirm_context)


def execute(
    state: AppState,
    ids: list[str],
    operation: Callable[[str], Outcome],
    options: WriteOptions,
    action: str,
    on_outcome: Callable[[Outcome], None] | None = None,
    noun: str = "things",
    reports_successes: bool = False,
) -> Summary:
    """Run the operation for all ids with progress, then print the summary.

    With ``--results``, each outcome is also printed as a JSON line on stdout, then a summary line;
    ``reports_successes`` means ``on_outcome`` already prints the successful ones (e.g. message responses).
    Raises BulkFailure (exit code 2) if things failed and InterruptedRunError (130) if interrupted.
    """
    samples: list[Outcome] = []

    failure_samples: list[Outcome] = []
    key = "policyId" if noun == "policies" else "thingId"

    def report(outcome: Outcome, sample: bool) -> None:
        if outcome.category == Category.PLANNED:
            wanted = options.results == "all" or sample
        elif outcome.category == Category.OK and reports_successes:
            wanted = False
        else:
            wanted = options.results == "all" or outcome.failed
        if wanted:
            output.line(result_line(outcome, key))

    def collect(outcome: Outcome) -> None:
        sample = outcome.category == Category.PLANNED and len(samples) < DRY_RUN_SAMPLES
        if sample:
            samples.append(outcome)
        if outcome.failed and len(failure_samples) < FAILURE_SAMPLES:
            failure_samples.append(outcome)
        if options.results != "none":
            report(outcome, sample)
        if on_outcome:
            on_outcome(outcome)

    journal = Journal(options.journal) if options.journal and not options.dry_run else None
    failure_log = FailureLog(options.failed_out) if options.failed_out and not options.dry_run else None

    def run(callback: Callable[[Outcome], None]) -> Summary:
        return run_bulk(
            ids,
            operation,
            concurrency=options.concurrency,
            rate=options.rate,
            journal=journal,
            resume=options.resume,
            failure_log=failure_log,
            on_outcome=callback,
        )

    if sys.stderr.isatty() and len(ids) > 1:
        progress = Progress(
            TextColumn(action.capitalize()),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=Console(emoji=False, file=sys.stderr),
            transient=True,
        )
        with progress:
            task = progress.add_task(action, total=len(ids))

            def advance(outcome: Outcome) -> None:
                progress.advance(task)
                collect(outcome)

            summary = run(advance)
    else:
        summary = run(collect)

    if options.results != "none":
        output.line({"summary": summary_line(summary, action, options.dry_run)})
    if options.dry_run:
        if options.results == "none":
            for sample in samples:
                output.info(f"would send for {sample.thing_id}:")
                output.emit(sample.detail)
        output.info(f"Dry run, nothing written. {summary.describe(noun)}")
    else:
        output.info(f"{action.capitalize()}: {summary.describe(noun)}")
    if summary.interrupted:
        hint = f"; resume with --journal {options.journal} --resume" if options.journal else ""
        raise InterruptedRunError(f"interrupted after {summary.processed} of {summary.total} {noun}{hint}")
    if summary.failures:
        for failure in failure_samples if options.results == "none" else []:
            reason = " ".join(p for p in (str(failure.status or ""), failure.error or "") if p)
            output.warn(f"{failure.thing_id}: {reason}: {failure.message or ''}".rstrip(": "))
            if failure.description:
                output.info(f"  {failure.description}")
        if summary.failures > len(failure_samples):
            output.info(f"... and {summary.failures - len(failure_samples)} more")
        where = f"; all failed {noun} are listed in {options.failed_out}" if options.failed_out else ""
        raise BulkFailure(f"{summary.failures} of {summary.total} {noun} failed{where}")
    return summary


def result_line(outcome: Outcome, key: str = "thingId") -> dict[str, Any]:
    """The JSON line of one thing's outcome for --results."""
    line: dict[str, Any] = {key: outcome.thing_id, "result": str(outcome.category)}
    for name in ("status", "error", "message", "description"):
        value = getattr(outcome, name)
        if value is not None:
            line[name] = value
    if outcome.category == Category.PLANNED:
        line["plan"] = outcome.detail
    return line


def summary_line(summary: Summary, action: str, dry_run: bool) -> dict[str, Any]:
    line: dict[str, Any] = {
        "action": action,
        "dryRun": dry_run,
        "total": summary.total,
        "processed": summary.processed,
        "counts": {str(category): n for category, n in summary.counts.most_common()},
        "failures": summary.failures,
        "elapsedSeconds": round(summary.elapsed, 3),
    }
    if summary.skipped_by_journal:
        line["skippedByJournal"] = summary.skipped_by_journal
    if summary.interrupted:
        line["interrupted"] = True
    return line

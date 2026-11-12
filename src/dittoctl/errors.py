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
"""Exception hierarchy and process exit codes."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

import httpx


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1
    PARTIAL_FAILURE = 2
    AUTH = 3
    NOT_FOUND = 4
    ABORTED = 5
    # a check found what it checks for: differences (diff), denied permissions, invalid RQL, mismatches (verify)
    CHECK_FAILED = 6
    INTERRUPTED = 130


class DittoctlError(Exception):
    """Base class for all errors dittoctl reports to the user."""

    exit_code: ExitCode = ExitCode.ERROR


class ConfigError(DittoctlError):
    pass


class AuthError(DittoctlError):
    exit_code = ExitCode.AUTH


class AbortedError(DittoctlError):
    exit_code = ExitCode.ABORTED


class CheckFailedError(DittoctlError):
    exit_code = ExitCode.CHECK_FAILED


class InterruptedRunError(DittoctlError):
    """A bulk run stopped with Ctrl+C; the things in flight were finished."""

    exit_code = ExitCode.INTERRUPTED


class DittoError(DittoctlError):
    """An error response returned by Ditto.

    Ditto error bodies have the shape
    ``{"status": 404, "error": "things:thing.notfound", "message": "...", "description": "...", "href": "..."}``.
    """

    def __init__(
        self,
        status: int,
        error: str | None = None,
        message: str | None = None,
        description: str | None = None,
        href: str | None = None,
        correlation_id: str | None = None,
        body: Any = None,
    ) -> None:
        self.status = status
        self.error = error
        self.message = message
        self.description = description
        self.href = href
        self.correlation_id = correlation_id
        self.body = body
        super().__init__(self._summary())

    @property
    def exit_code(self) -> ExitCode:  # type: ignore[override]
        if self.status == 401:
            return ExitCode.AUTH
        if self.status == 404:
            return ExitCode.NOT_FOUND
        return ExitCode.ERROR

    def _summary(self) -> str:
        head = f"{self.status}"
        if self.error:
            head += f" {self.error}"
        return f"{head}: {self.message}" if self.message else head

    @property
    def condition_failed(self) -> bool:
        """The request's RQL ``condition`` didn't match (e.g. ``things:condition.failed``).

        Not to be confused with ``things:precondition.failed`` (If-Match, If-None-Match, If-Equal: skip).
        """
        return self.status == 412 and (self.error or "").rpartition(":")[2] == "condition.failed"

    @staticmethod
    def is_error_body(body: Any) -> bool:
        """Whether a JSON value has the shape of a Ditto error, e.g. an error event within an SSE stream."""
        return isinstance(body, dict) and isinstance(body.get("status"), int) and isinstance(body.get("error"), str)

    @classmethod
    def from_body(cls, status: int, body: dict[str, Any], correlation_id: str | None = None) -> DittoError:
        return cls(
            status=status,
            error=body.get("error"),
            message=body.get("message"),
            description=body.get("description"),
            href=body.get("href"),
            correlation_id=correlation_id,
            body=body,
        )

    @classmethod
    def from_response(cls, response: httpx.Response) -> DittoError:
        correlation_id = response.headers.get("correlation-id")
        try:
            body = response.json()
        except ValueError:
            body = response.text or None
        if isinstance(body, dict):
            return cls.from_body(response.status_code, body, correlation_id)
        # an HTML error page (e.g. from a reverse proxy in front of Ditto) is useless on a terminal
        is_html = "html" in response.headers.get("content-type", "") or (
            isinstance(body, str) and body.lstrip().lower().startswith(("<html", "<!doctype"))
        )
        if isinstance(body, str) and body and not is_html:
            message: str | None = body
        else:
            message = response.reason_phrase or None
        # not an answer of Ditto itself (e.g. a proxy that doesn't route this path): say which request it was
        request = response.request
        description = f"{request.method} {request.url.path} was answered without a Ditto error"
        if response.status_code == 404:
            description += "; the endpoint may not be exposed by this installation (e.g. DevOps or status endpoints)"
        elif response.status_code in (502, 503, 504):
            description += "; a proxy in front of Ditto gave up, Ditto may still be processing the request"
        return cls(
            status=response.status_code,
            message=message,
            description=description,
            correlation_id=correlation_id,
            body=body,
        )

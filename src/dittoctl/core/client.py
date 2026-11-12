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
"""Thin HTTP client for the Ditto HTTP API.

Adds authentication, correlation ids, conditional headers, retries with backoff and Ditto error mapping
on top of httpx. It never prints; ``on_request``/``on_response`` hooks let the CLI show traffic.
"""

from __future__ import annotations

import itertools
import json as jsonlib
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from dittoctl import __version__
from dittoctl.auth.base import AuthProvider
from dittoctl.core.conditions import Conditions
from dittoctl.errors import DittoctlError, DittoError

RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
# requests that may be repeated without changing the outcome; merge PATCH is idempotent too
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"})
MAX_RETRY_DELAY_SECONDS = 30.0
MERGE_PATCH = "application/merge-patch+json"

_UNSET: Any = object()


@dataclass
class DittoResponse:
    status: int
    headers: httpx.Headers
    body: Any
    text: str

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag")

    @property
    def revision(self) -> int | None:
        value = self.headers.get("entity-revision")
        return int(value) if value and value.isdigit() else None

    @property
    def correlation_id(self) -> str | None:
        return self.headers.get("correlation-id")

    @classmethod
    def from_httpx(cls, response: httpx.Response) -> DittoResponse:
        body: Any = None
        if response.content:
            if "json" in response.headers.get("content-type", ""):
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
            else:
                body = response.text
        return cls(status=response.status_code, headers=response.headers, body=body, text=response.text)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


class DittoClient:
    def __init__(
        self,
        base_url: str,
        auth: AuthProvider | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool | str = True,
        max_retries: int = 3,
        backoff: float = 0.5,
        correlation_id: str | None = None,
        on_request: Callable[[httpx.Request], None] | None = None,
        on_response: Callable[[httpx.Response], None] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.max_retries = max_retries
        self.backoff = backoff
        self.run_id = correlation_id or f"dittoctl-{uuid.uuid4().hex[:12]}"
        self._sequence = itertools.count(1)
        self.on_request = on_request
        self.on_response = on_response
        self.sleep = sleep
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"User-Agent": f"dittoctl/{__version__}", **(headers or {})},
            timeout=timeout,
            verify=verify,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> DittoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def next_correlation_id(self) -> str:
        return f"{self.run_id}-{next(self._sequence)}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = _UNSET,
        data: Mapping[str, str] | None = None,
        content: str | bytes | None = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        conditions: Conditions | None = None,
        raise_for_status: bool = True,
        retry: bool | None = None,
        timeout: float | None = None,
    ) -> DittoResponse:
        """Send a request to ``path`` (relative to the base URL, e.g. ``/api/2/things/ns:id``).

        The body is ``json`` (serialized; merge patch for PATCH), ``data`` (form-encoded) or raw ``content``.
        ``retry`` defaults to True for idempotent methods; ``timeout`` overrides the client's timeout in seconds.
        Ditto error responses raise :class:`DittoError` unless ``raise_for_status`` is False.
        """
        method = method.upper()
        if json is not _UNSET:
            content = jsonlib.dumps(json)
            content_type = content_type or (MERGE_PATCH if method == "PATCH" else "application/json")
        elif data is not None:
            content = urlencode(data)
            content_type = content_type or "application/x-www-form-urlencoded"
        request_headers, request_params = self._prepare(path, params, content_type, headers, conditions)

        retry = method in IDEMPOTENT_METHODS if retry is None else retry
        refreshed = False
        attempt = 0
        while True:
            request = self._build(
                method,
                path,
                request_params,
                content,
                request_headers,
                timeout=httpx.Timeout(timeout) if timeout is not None else None,
            )
            try:
                response = self.http.send(request)
            except httpx.TransportError as e:
                if retry and attempt < self.max_retries:
                    self.sleep(self._delay(attempt, None))
                    attempt += 1
                    continue
                raise DittoctlError(f"{method} {request.url} failed: {e}") from e
            if self.on_response:
                self.on_response(response)

            if response.status_code == 401 and self.auth and not refreshed and self.auth.refresh():
                refreshed = True
                continue
            if response.status_code in RETRYABLE_STATUS and retry and attempt < self.max_retries:
                self.sleep(self._delay(attempt, response))
                attempt += 1
                continue
            if raise_for_status and response.status_code >= 400:
                raise DittoError.from_response(response)
            return DittoResponse.from_httpx(response)

    @contextmanager
    def stream(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> Iterator[httpx.Response]:
        """Open a streaming request, e.g. for server-sent events. The read timeout defaults to none."""
        request_headers, request_params = self._prepare(path, params, None, headers, None)
        timeout = httpx.Timeout(self.http.timeout.connect, read=read_timeout)
        refreshed = False
        while True:
            request = self._build(method.upper(), path, request_params, None, request_headers, timeout=timeout)
            try:
                response = self.http.send(request, stream=True)
            except httpx.TransportError as e:
                raise DittoctlError(f"{method} {request.url} failed: {e}") from e
            try:
                if self.on_response:
                    self.on_response(response)
                if response.status_code == 401 and self.auth and not refreshed and self.auth.refresh():
                    refreshed = True
                    continue
                if response.status_code >= 400:
                    response.read()
                    raise DittoError.from_response(response)
                yield response
                return
            finally:
                response.close()

    def _prepare(
        self,
        path: str,
        params: Mapping[str, Any] | None,
        content_type: str | None,
        headers: Mapping[str, str] | None,
        conditions: Conditions | None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        if not path.startswith("/"):
            raise DittoctlError(f"path must start with '/': {path}")
        request_headers: dict[str, str] = {}
        request_params: dict[str, Any] = dict(params or {})
        if conditions:
            request_headers.update(conditions.headers())
            request_params.update(conditions.params())
        if content_type:
            request_headers["Content-Type"] = content_type
        request_headers.update(headers or {})
        if not any(k.lower() == "correlation-id" for k in request_headers):
            request_headers["correlation-id"] = self.next_correlation_id()
        return request_headers, request_params

    def _build(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any],
        content: str | bytes | None,
        headers: Mapping[str, str],
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Request:
        # auth headers are fetched per attempt: a refresh after a 401 changes them
        auth_headers = self.auth.headers() if self.auth else {}
        extensions = {"timeout": timeout.as_dict()} if timeout else None
        request = self.http.build_request(
            method, path, params=params, content=content, headers={**auth_headers, **headers}, extensions=extensions
        )
        if self.on_request:
            self.on_request(request)
        return request

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        hinted = _retry_after(response) if response is not None else None
        delay = hinted if hinted is not None else self.backoff * (2**attempt)
        return min(delay, MAX_RETRY_DELAY_SECONDS)

    def get(self, path: str, **kwargs: Any) -> DittoResponse:
        return self.request("GET", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> DittoResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> DittoResponse:
        return self.request("PATCH", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> DittoResponse:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> DittoResponse:
        return self.request("DELETE", path, **kwargs)

    def whoami(self) -> Any:
        return self.get("/api/2/whoami").body

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
"""Ditto's conditional request options as one value object.

See https://eclipse.dev/ditto/httpapi-concepts.html#conditional-headers and
https://eclipse.dev/ditto/basic-conditional-requests.html
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class IfEqual(StrEnum):
    UPDATE = "update"
    SKIP = "skip"
    SKIP_MINIMIZING_MERGE = "skip-minimizing-merge"


class LiveTimeoutStrategy(StrEnum):
    FAIL = "fail"
    USE_TWIN = "use-twin"


def normalize_etag(value: str) -> str:
    """Ditto ETags look like ``"rev:5"``; accept ``rev:5`` as well and add the quotes.

    Proxies and CDNs that compress responses (nginx with gzip, Cloudflare) turn Ditto's strong ETags into
    weak ones (``W/"rev:5"``). Ditto compares ``If-Match`` strongly (as RFC 7232 requires) and, until
    https://github.com/eclipse-ditto/ditto/issues/2636 is fixed, ``If-None-Match`` too, so a weak ETag
    never matches. The ``W/`` prefix is dropped so that ETags received through such proxies work.
    """
    value = value.strip()
    if value.startswith("W/"):
        value = value[2:]
    if value == "*" or value.startswith('"'):
        return value
    return f'"{value}"'


@dataclass(frozen=True)
class Conditions:
    if_match: str | None = None
    if_none_match: str | None = None
    if_equal: IfEqual | None = None
    # RQL condition evaluated by Ditto against the current entity before applying the request
    condition: str | None = None
    # JSON pointer -> RQL; for merge (PATCH) requests on things, Ditto 3.8+
    patch_conditions: Mapping[str, str] = field(default_factory=dict)
    # RQL deciding whether a retrieve is routed to the live channel
    live_condition: str | None = None
    live_timeout_strategy: LiveTimeoutStrategy | None = None

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.if_match:
            headers["If-Match"] = normalize_etag(self.if_match)
        if self.if_none_match:
            headers["If-None-Match"] = normalize_etag(self.if_none_match)
        if self.if_equal:
            headers["If-Equal"] = str(self.if_equal)
        if self.patch_conditions:
            headers["merge-thing-patch-conditions"] = json.dumps(dict(self.patch_conditions), separators=(",", ":"))
        if self.live_timeout_strategy:
            headers["live-channel-timeout-strategy"] = str(self.live_timeout_strategy)
        return headers

    def params(self) -> dict[str, str]:
        # RQL expressions go into query parameters rather than headers, so that httpx URL-encodes them
        # and non-ASCII values are possible
        params: dict[str, str] = {}
        if self.condition:
            params["condition"] = self.condition
        if self.live_condition:
            params["live-channel-condition"] = self.live_condition
        return params

    def is_empty(self) -> bool:
        return not (self.headers() or self.params())

    def replace(self, **changes: object) -> Conditions:
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]

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
"""Policies: paths, discovery via things, subject migration and permission checks.

See https://eclipse.dev/ditto/basic-policy.html and https://eclipse.dev/ditto/httpapi-concepts.html
"""

from __future__ import annotations

import copy
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from dittoctl.core.bulk import Category, Outcome
from dittoctl.core.client import DittoClient
from dittoctl.core.conditions import Conditions
from dittoctl.core.search import find_things
from dittoctl.core.writes import Operation
from dittoctl.errors import DittoctlError, DittoError

POLICIES_PATH = "/api/2/policies"
CHECK_PERMISSIONS_PATH = "/api/2/checkPermissions"
ALLOW_LOCKOUT_PARAM = "allow-policy-lockout"


def policy_path(policy_id: str, *segments: str) -> str:
    """``policy_path("ns:p", "entries", "owner", "subjects", "nginx:ditto")``, each segment URL-encoded."""
    return f"{POLICIES_PATH}/{quote(policy_id, safe=':')}" + "".join(f"/{quote(s, safe=':')}" for s in segments if s)


def lockout_params(allow_lockout: bool) -> dict[str, str] | None:
    return {ALLOW_LOCKOUT_PARAM: "true"} if allow_lockout else None


def policy_ids_of_things(
    client: DittoClient, *, rql_filter: str | None, namespaces: Sequence[str] | None = None
) -> list[str]:
    """The distinct policy ids of the things matching the filter (Ditto has no search for policies)."""
    seen: dict[str, None] = {}
    for thing in find_things(client, rql_filter=rql_filter, namespaces=namespaces, fields="policyId"):
        if policy_id := thing.get("policyId"):
            seen.setdefault(policy_id)
    return list(seen)


@dataclass(frozen=True)
class SubjectChange:
    label: str
    old: str
    new: str
    removed_old: bool

    def describe(self) -> str:
        verb = "replace" if self.removed_old else "add"
        return f"{self.label}: {verb} {self.old} -> {self.new}"


def migrate_subjects(
    policy: dict[str, Any],
    pattern: re.Pattern[str],
    template: str,
    *,
    labels: Collection[str] | None = None,
    remove_old: bool = False,
) -> tuple[dict[str, Any], list[SubjectChange]]:
    """For each subject whose id fully matches ``pattern``, add a subject ``match.expand(template)`` with the same
    value (type, expiry, ...) to the same entry; with ``remove_old`` the old subject is removed. Idempotent: a
    subject that already exists is left as it is.
    """
    migrated = copy.deepcopy(policy)
    changes: list[SubjectChange] = []
    for label, entry in migrated.get("entries", {}).items():
        if labels and label not in labels:
            continue
        subjects: dict[str, Any] = entry.get("subjects", {})
        for subject_id in list(subjects):
            match = pattern.fullmatch(subject_id)
            if not match:
                continue
            new_id = match.expand(template)
            if new_id == subject_id:
                continue
            added = new_id not in subjects
            if added:
                subjects[new_id] = copy.deepcopy(subjects[subject_id])
            if remove_old:
                del subjects[subject_id]
            if added or remove_old:
                changes.append(SubjectChange(label, subject_id, new_id, remove_old))
    return migrated, changes


def subject_migration_operation(
    client: DittoClient,
    pattern: re.Pattern[str],
    template: str,
    *,
    labels: Collection[str] | None = None,
    remove_old: bool = False,
    allow_lockout: bool = False,
    conflict_retries: int = 3,
    dry_run: bool = False,
) -> Operation:
    """Migrate the subjects of each policy, written atomically per policy with ``If-Match``."""

    def operation(policy_id: str) -> Outcome:
        target = policy_path(policy_id)
        for _ in range(conflict_retries + 1):
            response = client.get(target)
            policy, etag = response.body, response.etag
            if not isinstance(policy, dict):
                raise DittoctlError(f"unexpected policy JSON for {policy_id}")
            migrated, changes = migrate_subjects(policy, pattern, template, labels=labels, remove_old=remove_old)
            if not changes:
                return Outcome(policy_id, Category.UNCHANGED, message="no matching subjects to migrate")
            described = [c.describe() for c in changes]
            if dry_run:
                return Outcome(policy_id, Category.PLANNED, detail={"policyId": policy_id, "changes": described})
            try:
                result = client.put(
                    target, json=migrated, conditions=Conditions(if_match=etag), params=lockout_params(allow_lockout)
                )
                return Outcome(policy_id, Category.OK, result.status, detail=described)
            except DittoError as e:
                if e.status != 412 or e.condition_failed:
                    raise
        return Outcome(
            policy_id,
            Category.CONFLICT,
            412,
            "conflict",
            f"modified concurrently {conflict_retries + 1} times in a row",
        )

    return operation


def check_permissions(client: DittoClient, checks: dict[str, dict[str, Any]]) -> dict[str, bool]:
    """Ask Ditto whether the caller has the given permissions; ``checks`` maps a name to
    ``{"resource": "thing:/attributes", "entityId": "ns:id", "hasPermissions": ["READ"]}``."""
    body = client.post(CHECK_PERMISSIONS_PATH, json=checks, retry=True).body
    if not isinstance(body, dict):
        raise DittoctlError(f"unexpected checkPermissions response: {body!r}")
    return body

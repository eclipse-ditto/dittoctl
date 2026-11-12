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
"""``dittoctl wot``: Web of Things integration."""

from __future__ import annotations

import click

from dittoctl.cli import output
from dittoctl.cli.state import AppState, pass_state
from dittoctl.core.things import wot_directory


@click.group("wot")
def wot_group() -> None:
    """Web of Things (WoT): Ditto's Thing Directory. See also 'things td' and 'things migrate-definition'."""


@wot_group.command("directory")
@pass_state
def directory(state: AppState) -> None:
    """Show Ditto's WoT Thing Directory description (/.well-known/wot, Ditto 3.9+)."""
    output.emit(wot_directory(state.client()))

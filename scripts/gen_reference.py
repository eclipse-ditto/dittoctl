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
"""Generate docs/reference.md from the help texts of all commands.

python scripts/gen_reference.py           # write docs/reference.md
python scripts/gen_reference.py --check   # exit 1 if docs/reference.md is outdated
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from dittoctl.cli.main import cli

TARGET = Path(__file__).resolve().parent.parent / "docs" / "reference.md"
HEADER = """# Command reference

Generated from the commands' help texts by `scripts/gen_reference.py`; don't edit by hand.

"""


def _commands(command: click.Command, path: list[str]) -> list[tuple[list[str], click.Command]]:
    found = [(path, command)]
    if isinstance(command, click.Group):
        for name in sorted(command.commands):
            found.extend(_commands(command.commands[name], [*path, name]))
    return found


def render() -> str:
    parts = [HEADER]
    for path, command in _commands(cli, ["dittoctl"]):
        name = " ".join(path)
        with click.Context(
            command, info_name=name, terminal_width=100, max_content_width=100, help_option_names=["-h", "--help"]
        ) as ctx:
            help_text = command.get_help(ctx)
        level = "#" * min(len(path) + 1, 4)
        parts.append(f"{level} `{name}`\n\n```text\n{help_text}\n```\n\n")
    return "".join(parts).rstrip("\n") + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print(f"{TARGET} is outdated; run python scripts/gen_reference.py", file=sys.stderr)
            return 1
        return 0
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

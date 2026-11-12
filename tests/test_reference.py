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
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gen_reference.py"


def test_reference_is_up_to_date():
    spec = importlib.util.spec_from_file_location("gen_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TARGET.read_text(encoding="utf-8") == module.render(), "run: python scripts/gen_reference.py"


def test_short_help_is_not_truncated_mid_sentence():
    import click

    from dittoctl.cli.main import cli

    def walk(command: click.Command, path: str):
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                yield f"{path} {name}", sub.get_short_help_str(limit=500)
                yield from walk(sub, f"{path} {name}")

    # click ends the short help at the first ". ", so "e.g." in a first sentence cuts it off
    truncated = [f"{name}: {short}" for name, short in walk(cli, "dittoctl") if short.endswith(("e.g.", "i.e."))]
    assert truncated == []


def test_every_option_has_help():
    import click

    from dittoctl.cli.main import cli

    def walk(command: click.Command, path: str):
        yield path, command
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                yield from walk(sub, f"{path} {name}")

    # people and LLMs alike rely on the help texts; an option without one is a guess
    missing = [
        f"{path} {param.opts[0]}"
        for path, command in walk(cli, "dittoctl")
        for param in command.params
        if isinstance(param, click.Option) and not param.help and "--help" not in param.opts
    ]
    assert missing == []

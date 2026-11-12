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
"""Entry point: the root command group, global options and error handling."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import click
from click.shell_completion import get_completion_class

from dittoctl import __version__
from dittoctl.cli import output
from dittoctl.cli.api_cmd import api, whoami
from dittoctl.cli.auth_cmd import auth_group
from dittoctl.cli.config_cmd import complete_context_names, config_group
from dittoctl.cli.connections_cmd import connections_group
from dittoctl.cli.devops_cmd import devops_group
from dittoctl.cli.messages_cmd import messages_group
from dittoctl.cli.options import parse_key_value
from dittoctl.cli.policies_cmd import policies_group
from dittoctl.cli.rql_cmd import rql_group
from dittoctl.cli.state import AppState
from dittoctl.cli.things_cmd import things_group
from dittoctl.cli.things_write_cmd import array_group  # noqa: F401 - registers the write commands
from dittoctl.cli.wot_cmd import wot_group
from dittoctl.errors import DittoctlError, ExitCode

COMPLETE_VAR = "_DITTOCTL_COMPLETE"


@click.group(context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 120})
@click.version_option(__version__, "-V", "--version", prog_name="dittoctl")
@click.option(
    "-c",
    "--context",
    "context_name",
    envvar="DITTOCTL_CONTEXT",
    shell_complete=complete_context_names,
    help="Context to use instead of the current one. [env: DITTOCTL_CONTEXT]",
)
@click.option(
    "--url",
    envvar="DITTOCTL_URL",
    help="Ditto base URL. Without --context, credentials come from DITTOCTL_TOKEN or "
    "DITTOCTL_USERNAME/DITTOCTL_PASSWORD. [env: DITTOCTL_URL]",
)
@click.option(
    "-H", "--header", "headers", multiple=True, metavar="NAME:VALUE", help="Extra request header. Repeatable."
)
@click.option("--timeout", type=float, help="Request timeout in seconds.")
@click.option("--correlation-id", help="Prefix for the correlation-id of each request (default: random per run).")
@click.option("-v", "--verbose", count=True, help="-v prints requests as curl commands, -vv also response headers.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    envvar="DITTOCTL_CONFIG",
    help="Config file. [env: DITTOCTL_CONFIG]",
)
@click.option(
    "--agent/--no-agent",
    default=None,
    envvar="DITTOCTL_AGENT",
    # applied while parsing, so that it also holds for errors before the command runs, e.g. a mistyped command
    callback=lambda _ctx, _param, value: output.set_agent_mode(value),
    expose_value=False,
    help="Output for AI agents: single-line JSON, errors as JSON, limited result sizes, per-thing results of "
    "bulk writes, no writes to protected contexts. Default: on if CLAUDECODE or AI_AGENT is set. "
    "[env: DITTOCTL_AGENT]",
)
@click.pass_context
def cli(
    ctx: click.Context,
    context_name: str | None,
    url: str | None,
    headers: tuple[str, ...],
    timeout: float | None,
    correlation_id: str | None,
    verbose: int,
    config_path: Path | None,
) -> None:
    """dittoctl - command line tool for Eclipse Ditto."""
    state = AppState(
        context_name=context_name,
        url=url,
        verbose=verbose,
        extra_headers=parse_key_value(headers, "--header", ":="),
        timeout=timeout,
        correlation_id=correlation_id,
        config_path=config_path,
    )
    ctx.obj = state
    ctx.call_on_close(state.close)


@click.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Print the shell completion script.

    \b
    bash:  eval "$(dittoctl completion bash)"
    zsh:   eval "$(dittoctl completion zsh)"
    fish:  dittoctl completion fish | source
    """
    completion_class = get_completion_class(shell)
    assert completion_class is not None
    click.echo(completion_class(cli, {}, "dittoctl", COMPLETE_VAR).source())


cli.add_command(config_group)
cli.add_command(auth_group)
cli.add_command(whoami)
cli.add_command(things_group)
cli.add_command(rql_group)
cli.add_command(messages_group)
cli.add_command(policies_group)
cli.add_command(connections_group)
cli.add_command(devops_group)
cli.add_command(wot_group)
cli.add_command(api)
cli.add_command(completion)


def _usage_error(e: click.ClickException) -> None:
    if not output.agent_mode():
        e.show()
        return
    usage = None
    if isinstance(e, click.UsageError) and e.ctx is not None:
        usage = f"{e.ctx.get_usage()} (see {e.ctx.command_path} --help)"
    output.error_json(ExitCode.ERROR, e.format_message(), error="usage", usage=usage)


def _stopped(exit_code: int, message: str) -> int:
    if output.agent_mode():
        output.error_json(exit_code, message)
    else:
        output.info(message)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    # until the root command has parsed --agent/--no-agent, e.g. for errors in the global options
    output.set_agent_mode(None)
    try:
        result = cli.main(args=argv, prog_name="dittoctl", standalone_mode=False, complete_var=COMPLETE_VAR)
    except click.exceptions.Abort:
        return _stopped(ExitCode.ABORTED, "Aborted.")
    except click.ClickException as e:
        _usage_error(e)
        return ExitCode.ERROR
    except DittoctlError as e:
        output.error(e)
        return e.exit_code
    except KeyboardInterrupt:
        return _stopped(ExitCode.INTERRUPTED, "Interrupted.")
    # in non-standalone mode click returns the exit code for --help/--version, else the command's return value
    return result if isinstance(result, int) else ExitCode.OK

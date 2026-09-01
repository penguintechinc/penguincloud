"""`pcli` entry point.

Wires the static commands (`login`/`logout`/`whoami`/`products`/`tenants`)
and the manifest-discovered product tree
(`pcli.commands.resource_group.PcliGroup`) into one root group, resolves
`CLIConfig` once per invocation, and translates any `PcliError` into an
exit code -- see `main()`.
"""

from __future__ import annotations

import sys

import click

from . import __version__
from .commands.auth_cmds import login, logout, whoami
from .commands.products_cmds import products_group
from .commands.resource_group import PcliGroup, resolve_app_state
from .commands.tenants_cmds import tenants_group
from .config import ENV_PORTAL_URL
from .errors import PcliError
from .exit_codes import EXIT_GENERAL

#: Every always-present command, keyed by the name `pcli <name>` dispatches
#: on. Built once, at import time -- `PcliGroup` never mutates this dict.
_STATIC_COMMANDS: dict[str, click.Command] = {
    "login": login,
    "logout": logout,
    "whoami": whoami,
    "products": products_group,
    "tenants": tenants_group,
}


@click.group(cls=PcliGroup, static_commands=_STATIC_COMMANDS)
@click.option(
    "--portal-url",
    envvar=ENV_PORTAL_URL,
    default=None,
    help=f"Portal base URL, e.g. https://portal.penguincloud.io. Or set {ENV_PORTAL_URL}.",
)
@click.version_option(version=__version__, prog_name="pcli")
@click.pass_context
def cli(ctx: click.Context, portal_url: str | None) -> None:
    """Pcli -- the PenguinCloud portal command-line client.

    Its `<product> <resource>` command tree is discovered from your
    tenant's connected products at runtime (`pcli products list` shows
    what's available) -- there is no per-product subcommand to look up in
    a changelog.
    """
    # `portal_url` (this callback's own parsed param) is unused directly:
    # `resolve_app_state` re-reads it from `ctx.params` because it must
    # also work when CALLED FIRST from `PcliGroup.get_command`/
    # `list_commands`, which run before this callback -- see that
    # function's own docstring. Calling it here (rather than duplicating
    # its body) guarantees this callback and the group's dispatch hooks
    # always agree on one `AppState` per invocation.
    del portal_url
    resolve_app_state(ctx)


def main() -> None:
    """Console-script entry point (`pyproject.toml`'s `[project.scripts]`).

    The one place a `PcliError` is caught and turned into `(message on
    stderr, matching exit code)` -- every command below raises rather than
    calling `sys.exit` itself, so the exit-code taxonomy
    (`pcli.exit_codes`) is applied in exactly one place.
    """
    try:
        cli(standalone_mode=False)
    except PcliError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(exc.exit_code)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.Exit as exc:
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(EXIT_GENERAL)


if __name__ == "__main__":
    main()

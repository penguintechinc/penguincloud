"""Tests for `pcli.cli` -- root group wiring, exit codes, `--help` without a portal URL.

`main()` (not the bare `cli` Click object) is what actually applies pcli's
own exit-code taxonomy (`click.testing.CliRunner.invoke` on `cli` directly
would use CLICK's default exception handling instead, which reports a
bare `1` for any uncaught exception and would silently defeat these
assertions) -- see `cli.py`'s own docstring for why that mapping lives in
exactly one place.
"""

from __future__ import annotations

import sys

import pytest
from click.testing import CliRunner

from pcli.cli import cli, main
from pcli.exit_codes import EXIT_CONFIG


def test_root_help_does_not_require_portal_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pcli --help` with no PCLI_PORTAL_URL/--portal-url must not crash.

    Click resolves `--help` at the ROOT level before the root callback
    (which would otherwise raise ConfigurationError) ever runs -- see
    `PcliGroup.list_commands`'s own docstring for why.
    """
    monkeypatch.delenv("PCLI_PORTAL_URL", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "products" in result.output
    assert "tenants" in result.output


def test_version_flag() -> None:
    """Version flag."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "pcli" in result.output


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    """Run `main()` and return the effective process exit code.

    `main()` only calls `sys.exit(...)` explicitly on an error path -- a
    successful invocation (e.g. `--help`) falls through to a normal
    `return`, which is still an exit-0 process in practice (Python's
    default), just not a raised `SystemExit` here.
    """
    monkeypatch.setattr(sys, "argv", ["pcli", *args])
    try:
        main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def test_main_maps_configuration_error_to_exit_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main maps configuration error to exit config."""
    monkeypatch.delenv("PCLI_PORTAL_URL", raising=False)
    code = _run_main(monkeypatch, ["whoami"])
    assert code == EXIT_CONFIG
    assert "No portal URL configured" in capsys.readouterr().err


def test_main_maps_unknown_subcommand_config_error_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even `pcli some-unconfigured-product ...` needs a portal URL to attempt discovery."""
    monkeypatch.delenv("PCLI_PORTAL_URL", raising=False)
    code = _run_main(monkeypatch, ["not-a-real-product", "resource", "list"])
    assert code == EXIT_CONFIG


def test_main_exits_zero_on_help(monkeypatch: pytest.MonkeyPatch) -> None:
    """Main exits zero on help."""
    code = _run_main(monkeypatch, ["--help"])
    assert code == 0

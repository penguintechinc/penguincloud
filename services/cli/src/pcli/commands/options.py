"""Shared Click option decorators for leaf commands (static and discovered alike)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

import click

from ..config import OUTPUT_FORMATS, AppState

F = TypeVar("F", bound=Callable[..., Any])


def output_options(func: F) -> F:
    """Attach `-o/--output {table,json,yaml}` and `--query <jmespath>` to a command."""
    func = click.option(
        "--query",
        default=None,
        help="jmespath expression to narrow the response before rendering.",
    )(func)
    func = click.option(
        "-o",
        "--output",
        "output",
        type=click.Choice(OUTPUT_FORMATS),
        default=None,
        help="Output format. Defaults to 'table' on a TTY, 'json' otherwise.",
    )(func)
    return func


def resolved_config(ctx: click.Context, output: str | None, query: str | None) -> Any:
    """Merge a leaf command's own `-o`/`--query` onto the root `AppState.config`.

    `state.config.output` was already resolved to a concrete choice (never
    None) by `cli.py`'s root group callback, via `detect_default_format()` --
    so a leaf command that did not pass `-o` simply inherits it.
    """
    state: AppState = ctx.obj
    resolved_output = output if output is not None else state.config.output
    return replace(state.config, output=resolved_output, query=query)

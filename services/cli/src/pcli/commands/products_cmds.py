"""`pcli products list` -- every connected product's manifest, for this tenant."""

from __future__ import annotations

import asyncio
from typing import Any

import click

from ..output import render_generic
from ..session import build_portal_client, ensure_valid_token
from .options import output_options, resolved_config


@click.group("products")
def products_group() -> None:
    """Product connections for the active tenant."""


@products_group.command("list")
@output_options
@click.pass_context
def products_list(ctx: click.Context, output: str | None, query: str | None) -> None:
    """List every product this tenant is connected to (`GET /console/manifests`).

    Sourced from `/console/manifests` rather than `/products`, per the
    design brief: it is the same document that drives command discovery
    (`pcli.commands.resource_group`), so `pcli products list` shows exactly
    the product set `pcli <product> ...` will resolve, including the
    subtract-only capabilities overlay a plain `/products` connection
    listing does not apply.
    """
    config = resolved_config(ctx, output, query)

    async def _run() -> list[dict[str, Any]]:
        tokens = await ensure_valid_token(config)
        async with build_portal_client(config, tokens) as portal:
            entries = await portal.list_manifests()
        return [
            {
                "product_id": e.product_id,
                "product_type": e.product_type,
                "display_name": e.manifest.display_name,
                "resources": [r.kind for r in e.manifest.resources],
            }
            for e in entries
        ]

    rows = asyncio.run(_run())
    click.echo(render_generic(rows, output=config.output, query=config.query))

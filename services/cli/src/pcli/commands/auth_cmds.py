"""`pcli login` / `logout` / `whoami`."""

from __future__ import annotations

import asyncio
from typing import Any

import click
import httpx

from ..auth.device_flow import DeviceFlowClient
from ..auth.keyring_store import TokenStore
from ..auth.tokens import decode_jwt_claims
from ..config import AppState
from ..output import render_generic
from ..session import build_portal_client, ensure_valid_token
from .options import output_options, resolved_config


@click.command("login")
@click.pass_context
def login(ctx: click.Context) -> None:
    """Log in via the RFC 8628 device authorization grant (`app.device_auth`)."""
    state: AppState = ctx.obj
    config = state.config

    async def _run() -> None:
        async with httpx.AsyncClient(base_url=config.portal_url, timeout=config.timeout) as http:
            flow = DeviceFlowClient(http)
            authorization = await flow.authorize()
            click.echo(
                f"To finish logging in, visit:\n\n"
                f"    {authorization.verification_uri_complete}\n"
            )
            click.echo(
                f"Or go to {authorization.verification_uri} and enter code: "
                f"{authorization.user_code}\n"
            )
            click.echo("Waiting for approval...")
            tokens = await flow.poll_for_token(authorization)
        TokenStore(config.host_key).save(tokens)
        click.echo("Login successful.")

    asyncio.run(_run())


@click.command("logout")
@click.pass_context
def logout(ctx: click.Context) -> None:
    """Discard the stored credential for this portal host."""
    state: AppState = ctx.obj
    TokenStore(state.config.host_key).clear()
    click.echo("Logged out.")


@click.command("whoami")
@output_options
@click.pass_context
def whoami(ctx: click.Context, output: str | None, query: str | None) -> None:
    """Show the current identity, active tenant, and token scopes."""
    config = resolved_config(ctx, output, query)

    async def _run() -> dict[str, Any]:
        tokens = await ensure_valid_token(config)
        async with build_portal_client(config, tokens) as portal:
            profile = await portal.me()
        claims = decode_jwt_claims(tokens.access_token)
        return {
            **profile,
            "tenant": (
                {"id": tokens.tenant.id, "slug": tokens.tenant.slug, "name": tokens.tenant.name}
                if tokens.tenant
                else claims.get("tenant")
            ),
            "scope": list(tokens.scope) or claims.get("scope", []),
            "teams": claims.get("teams", []),
        }

    result = asyncio.run(_run())
    click.echo(render_generic(result, output=config.output, query=config.query))

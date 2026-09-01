"""`pcli tenants list` / `pcli tenants use <slug-or-id>`."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import click

from ..auth.keyring_store import TokenStore
from ..auth.tokens import TenantContext, TokenSet, decode_jwt_claims
from ..errors import PcliError
from ..exit_codes import EXIT_NOT_FOUND
from ..output import render_generic
from ..session import build_portal_client, ensure_valid_token
from .options import output_options, resolved_config

#: Fallback token lifetime when a `/switch` response's re-issued access
#: token carries no readable `exp` claim -- security.md's own default JWT
#: expiry (1h), used only as a last resort so a token pcli cannot introspect
#: is still treated as eventually expiring rather than as immortal.
_DEFAULT_TOKEN_TTL_SECONDS: float = 3600.0


@click.group("tenants")
def tenants_group() -> None:
    """Tenant membership and the active-tenant switch."""


@tenants_group.command("list")
@click.option(
    "--include-children",
    is_flag=True,
    default=False,
    help="Also list tenants in subtrees the caller administers (summaries only).",
)
@output_options
@click.pass_context
def tenants_list(
    ctx: click.Context, include_children: bool, output: str | None, query: str | None
) -> None:
    """List tenants the caller is a member of (`GET /tenants`)."""
    config = resolved_config(ctx, output, query)

    async def _run() -> list[dict[str, Any]]:
        tokens = await ensure_valid_token(config)
        async with build_portal_client(config, tokens) as portal:
            return await portal.list_tenants(include_children=include_children)

    rows = asyncio.run(_run())
    click.echo(render_generic(rows, output=config.output, query=config.query))


@tenants_group.command("use")
@click.argument("tenant")
@click.pass_context
def tenants_use(ctx: click.Context, tenant: str) -> None:
    """Switch the active tenant, by numeric id or slug (`POST /tenants/{id}/switch`).

    Re-issues a tenant-scoped JWT the same way the webui's own tenant
    switcher does (`portalUrl.tenantSwitch`) -- `pcli` cannot reach a tenant
    the caller is not otherwise authorized into, since it calls the exact
    same authorization-checked endpoint.
    """
    config = resolved_config(ctx, output=None, query=None)

    async def _run() -> TokenSet:
        tokens = await ensure_valid_token(config)
        async with build_portal_client(config, tokens) as portal:
            candidates = await portal.list_tenants(include_children=True)
            tenant_id = _resolve_tenant_id(tenant, candidates)
            response = await portal.switch_tenant(tenant_id)
        return _token_set_from_switch(response, previous=tokens)

    new_tokens = asyncio.run(_run())
    TokenStore(config.host_key).save(new_tokens)
    name = new_tokens.tenant.name if new_tokens.tenant else tenant
    click.echo(f"Switched to tenant: {name}")


def _resolve_tenant_id(tenant: str, candidates: list[dict[str, Any]]) -> int:
    """Resolve a `pcli tenants use` argument (numeric id or slug) to a tenant id."""
    if tenant.isdigit():
        target_id = int(tenant)
        for row in candidates:
            if row.get("id") == target_id:
                return target_id
    for row in candidates:
        if row.get("slug") == tenant:
            row_id = row.get("id")
            if isinstance(row_id, int):
                return row_id
    raise PcliError(f"No tenant matching {tenant!r} in your tenant list.", exit_code=EXIT_NOT_FOUND)


def _token_set_from_switch(response: dict[str, Any], *, previous: TokenSet) -> TokenSet:
    """Build the post-switch `TokenSet`.

    `TenantSwitchResponse` carries a fresh `access_token` but no
    `refresh_token`/`expires_in` (see `openapi/v1.yaml`'s schema and its own
    docstring) -- the prior `refresh_token` is reused unchanged (switching
    tenants does not revoke it), and `expires_at` is recomputed from the new
    access token's own `exp` claim (best-effort, UNVERIFIED decode -- see
    `decode_jwt_claims`) since the response declares no `expires_in` to
    compute it from directly.
    """
    access_token = response["access_token"]
    claims = decode_jwt_claims(access_token)
    exp = claims.get("exp")
    if isinstance(exp, int | float):
        expires_at = float(exp)
    else:
        expires_at = time.time() + _DEFAULT_TOKEN_TTL_SECONDS
    tenant_body = response.get("tenant") or {}
    tenant_context = TenantContext(
        id=tenant_body.get("id", 0),
        slug=tenant_body.get("slug"),
        name=tenant_body.get("name"),
    )
    return TokenSet(
        access_token=access_token,
        refresh_token=previous.refresh_token,
        token_type="Bearer",  # noqa: S106 -- an auth SCHEME name, not a credential
        expires_at=expires_at,
        tenant=tenant_context,
        scope=tuple(response.get("scope", ())),
    )

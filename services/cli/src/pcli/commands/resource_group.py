"""The manifest-discovered command tree: `pcli <product> <resource> list/get`.

This is the whole point of `pcli`'s command-tree design (see the repo's
Phase 8 design brief): `PcliGroup.list_commands`/`get_command` build the
`<product>` and `<resource>` levels FROM `GET /api/v1/console/manifests`
data at runtime, not from a hardcoded per-product Python module. A new
product appearing in a tenant's manifest set produces new `pcli`
subcommands with zero code change here -- proven by
`tests/commands/test_resource_group.py::test_synthetic_product_discovered`,
which injects a synthetic product+resource into a fake manifest source and
asserts `pcli <that-product> <that-resource> list` resolves and runs.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import click
import httpx

from ..api.client import to_proxy_path, unwrap_envelope
from ..api.manifest_cache import ManifestCache
from ..api.manifest_types import ItemPathSpec, ListSpec, ProductManifestEntry, ResourceDescriptor
from ..auth.tokens import TokenSet
from ..config import AppState, CLIConfig, build_config
from ..errors import PcliError
from ..output import detect_default_format, render_resource_rows
from ..session import build_portal_client, ensure_valid_token
from .options import output_options, resolved_config


def resolve_app_state(ctx: click.Context) -> AppState:
    """Build (or reuse) this invocation's `AppState` from `ctx.params`.

    Click resolves a `MultiCommand`'s subcommand (`get_command`/
    `list_commands`) BEFORE invoking the group's own callback --
    `MultiCommand.invoke`'s `resolve_command(...)` call precedes
    `super().invoke(ctx)`, which is what actually runs `cli.py`'s root
    callback. So `ctx.obj` is NOT yet set the first time `PcliGroup.
    get_command`/`list_commands` run for a given invocation. This reads the
    already-parsed `--portal-url` value straight from `ctx.params`
    (populated by `parse_args`, which DOES run before `invoke`) rather than
    depending on callback order, and caches the result on `ctx.obj` so the
    callback -- and every leaf command after it -- reuses the same
    `AppState` instead of rebuilding it.
    """
    if ctx.obj is not None:
        return cast(AppState, ctx.obj)
    portal_url = ctx.params.get("portal_url")
    state = AppState(config=build_config(portal_url=portal_url, output=detect_default_format()))
    ctx.obj = state
    return state


def _current_tenant_id(tokens: TokenSet) -> int | None:
    """The tenant id a manifest fetch should be cached under, if one is known.

    `None` when the current token carries no tenant context at all (a
    freshly device-flow-issued token before any `pcli tenants use` --
    `app.device_auth`'s own docstring: the grant "mirrors login's own
    current unscoped-tenant shape"). Caching is skipped entirely in that
    case rather than writing under a placeholder id -- see
    `ManifestProvider._load`.
    """
    if tokens.tenant is not None:
        return tokens.tenant.id
    return None


class ManifestProvider:
    """Resolves the active tenant's product manifests: cache first, live fallback.

    `entries()` is a plain SYNC method (Click's `list_commands`/
    `get_command` are sync) that drives the async fetch underneath via
    `asyncio.run` and memoizes the result for the lifetime of one pcli
    invocation -- `pcli gough nodes list` must not fetch the manifest set
    twice (once for command resolution, once for rendering).
    """

    def __init__(self, config: CLIConfig) -> None:
        """Bind this provider to one invocation's resolved config."""
        self._config = config
        self._entries: tuple[ProductManifestEntry, ...] | None = None
        #: Set by `_load` when the returned entries came from a stale cache
        #: (client.md: "Stale data awareness") -- read by `PcliGroup` to
        #: decide whether to print a warning.
        self.served_from_stale_cache: bool = False

    def entries(self) -> tuple[ProductManifestEntry, ...]:
        """This invocation's product manifests, fetched at most once."""
        if self._entries is None:
            self._entries = asyncio.run(self._load())
        return self._entries

    async def _load(self) -> tuple[ProductManifestEntry, ...]:
        tokens = await ensure_valid_token(self._config)
        tenant_id = _current_tenant_id(tokens)
        cache = ManifestCache(self._config.host_key) if tenant_id is not None else None
        try:
            async with build_portal_client(self._config, tokens) as portal:
                entries = await portal.list_manifests()
        except (PcliError, httpx.HTTPError):
            if cache is not None and tenant_id is not None:
                cached = cache.load(tenant_id)
                if cached is not None:
                    self.served_from_stale_cache = True
                    return cached.entries
            raise
        if cache is not None and tenant_id is not None:
            cache.save(tenant_id, entries)
        return entries


def build_product_group(
    product_type: str, entries: tuple[ProductManifestEntry, ...]
) -> click.Group:
    """Build the `pcli <product_type>` group: one subgroup per resource kind.

    `entries` is every connection of this product type in the tenant --
    almost always one. When there is more than one, every leaf command
    exposes `--connection <id>` to pick which; it defaults to the first.
    """
    canonical = entries[0]
    entries_by_id = {e.product_id: e for e in entries}

    group = click.Group(
        name=product_type,
        help=f"{canonical.manifest.display_name} ({product_type})",
    )
    for resource in canonical.manifest.resources:
        list_spec = resource.list
        item_path = resource.item_path
        if list_spec is None and item_path is None:
            # A resource with neither a list nor an item route has no read
            # path this schema version can express (see
            # `ResourceDescriptor`'s own docstring, e.g. Gough's `clusters`)
            # -- nothing to attach a `pcli` subcommand to.
            continue
        resource_group = click.Group(name=resource.kind, help=resource.plural_label)
        if list_spec is not None:
            resource_group.add_command(_build_list_command(resource, list_spec, entries_by_id))
        if item_path is not None:
            resource_group.add_command(_build_get_command(resource, item_path, entries_by_id))
        group.add_command(resource_group)
    return group


def _resolve_connection_id(
    connection_id: int | None, entries_by_id: dict[int, ProductManifestEntry]
) -> int:
    if connection_id is None:
        return next(iter(entries_by_id))
    if connection_id not in entries_by_id:
        raise PcliError(
            f"--connection {connection_id} is not a connection of this product "
            f"in the active tenant. Known connection ids: "
            f"{', '.join(str(i) for i in entries_by_id)}."
        )
    return connection_id


def _build_list_command(
    resource: ResourceDescriptor,
    list_spec: ListSpec,
    entries_by_id: dict[int, ProductManifestEntry],
) -> click.Command:
    """Build the `list` leaf command for one manifest-discovered resource."""

    @click.command("list", help=f"List {resource.plural_label}.")
    @click.option(
        "--connection",
        "connection_id",
        type=int,
        default=None,
        help="Product connection id, if this product has more than one connection.",
    )
    @output_options
    @click.pass_context
    def _list(
        ctx: click.Context, connection_id: int | None, output: str | None, query: str | None
    ) -> None:
        config = resolved_config(ctx, output, query)
        target_id = _resolve_connection_id(connection_id, entries_by_id)

        async def _run() -> list[dict[str, Any]]:
            tokens = await ensure_valid_token(config)
            async with build_portal_client(config, tokens) as portal:
                proxy_path = to_proxy_path(list_spec.path_bytes)
                raw = await portal.proxy_get(target_id, proxy_path)
            return unwrap_envelope(raw, list_spec.envelope)

        rows = asyncio.run(_run())
        click.echo(
            render_resource_rows(rows, resource.columns, output=config.output, query=config.query)
        )

    return _list


def _build_get_command(
    resource: ResourceDescriptor,
    item_path: ItemPathSpec,
    entries_by_id: dict[int, ProductManifestEntry],
) -> click.Command:
    """Build the `get` leaf command for one manifest-discovered resource."""

    @click.command("get", help=f"Get one {resource.label} by id.")
    @click.argument("resource_id")
    @click.option(
        "--connection",
        "connection_id",
        type=int,
        default=None,
        help="Product connection id, if this product has more than one connection.",
    )
    @output_options
    @click.pass_context
    def _get(
        ctx: click.Context,
        resource_id: str,
        connection_id: int | None,
        output: str | None,
        query: str | None,
    ) -> None:
        config = resolved_config(ctx, output, query)
        target_id = _resolve_connection_id(connection_id, entries_by_id)

        async def _run() -> dict[str, Any]:
            tokens = await ensure_valid_token(config)
            async with build_portal_client(config, tokens) as portal:
                proxy_path = to_proxy_path(f"{item_path.prefix}/{resource_id}")
                result: dict[str, Any] = await portal.proxy_get(target_id, proxy_path)
                return result

        row = asyncio.run(_run())
        click.echo(
            render_resource_rows([row], resource.columns, output=config.output, query=config.query)
        )

    return _get


class PcliGroup(click.Group):
    """The root Click group: static commands + a manifest-discovered product tree.

    `list_commands`/`get_command` are `click.MultiCommand`'s own lazy-
    loading hook (see the Click docs' "complex" example) -- overridden here
    so the `<product>` level of the tree is never enumerated ahead of time.
    """

    def __init__(
        self, *args: Any, static_commands: dict[str, click.Command], **kwargs: Any
    ) -> None:
        """`static_commands` are always present (login/logout/whoami/products/tenants)."""
        super().__init__(*args, **kwargs)
        self._static = static_commands

    def _manifest_provider(self, ctx: click.Context) -> ManifestProvider:
        """This invocation's `ManifestProvider` -- cached on `ctx.obj`, never on `self`.

        `self` is a module-level singleton (`cli.py`'s `cli` object) reused
        across every invocation in a process; caching the provider there
        would leak one invocation's manifest snapshot into the next -- see
        `AppState.manifest_provider`'s own docstring for the concrete
        failure this fixes (a multi-connection product silently losing its
        second connection on a later call).
        """
        state = resolve_app_state(ctx)
        if state.manifest_provider is None:
            state.manifest_provider = ManifestProvider(state.config)
        return cast(ManifestProvider, state.manifest_provider)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Static command names + every discoverable product type.

        Best-effort: `--help`/tab-completion must not crash just because
        no portal URL is configured, the caller is not logged in, or the
        portal is briefly unreachable -- any of those (all `PcliError`/
        `httpx.HTTPError`) degrade to the static command set. Contrast
        `get_command` below, which lets the same failure propagate with an
        actionable message once the caller has actually named a product.
        """
        names = set(self._static)
        try:
            entries = self._manifest_provider(ctx).entries()
        except (PcliError, httpx.HTTPError):
            entries = ()
        names.update(e.product_type for e in entries)
        return sorted(names)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Resolve a static command, else a discovered product group, else None."""
        static = self._static.get(cmd_name)
        if static is not None:
            return static
        provider = self._manifest_provider(ctx)
        entries = provider.entries()
        if provider.served_from_stale_cache:
            click.echo(
                "warning: showing a cached manifest (portal was unreachable); "
                "data below may also be stale.",
                err=True,
            )
        matches = tuple(e for e in entries if e.product_type == cmd_name)
        if not matches:
            return None
        return build_product_group(cmd_name, matches)

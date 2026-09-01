"""The falsification test: a synthetic product+resource -> working `pcli` subcommands.

Zero code change to `pcli.commands.resource_group` required. This is the
headline proof for the whole `pcli` design -- `pcli <product> <resource>
list/get` must come entirely from manifest data, never a hardcoded
per-product Python module. Every test here builds a `ProductManifestEntry`
in-test (nothing pcli's source tree has ever seen) and drives
`PcliGroup`/`build_product_group` directly against it.
"""

from __future__ import annotations

import time
from typing import Any

import click
import httpx
import pytest
from click.testing import CliRunner

from pcli.api.manifest_types import (
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    EnvelopeSpec,
    ItemPathSpec,
    ListSpec,
    ProductManifestEntry,
    ResourceDescriptor,
)
from pcli.auth.keyring_store import TokenStore
from pcli.auth.tokens import TokenSet
from pcli.commands.resource_group import PcliGroup, build_product_group
from pcli.config import build_config

#: A product+resource pair that exists ONLY inside this test file -- proof
#: that nothing under src/pcli names "waddle-farm" or "widgets" anywhere.
_SYNTHETIC_PRODUCT_TYPE = "waddle-farm"
_SYNTHETIC_RESOURCE_KIND = "widgets"


def _synthetic_entry(product_id: int = 55) -> ProductManifestEntry:
    columns = (
        ColumnSpec(field="id", label="ID", cell=CellSpec(kind="text")),
        ColumnSpec(
            field="owner_team",
            label="Owner",
            cell=CellSpec(kind="text"),
            absent_as="literal:Unassigned",
        ),
    )
    resource = ResourceDescriptor(
        kind=_SYNTHETIC_RESOURCE_KIND,
        label="Widget",
        plural_label="Widgets",
        id_field="id",
        name_field="name",
        transport="proxy",
        columns=columns,
        empty_state="No widgets.",
        error_state="Unable to load widgets.",
        list=ListSpec(
            path_bytes="/api/v1/widgets/",
            envelope=EnvelopeSpec(keys=("widgets",)),
            pagination="cursor",
        ),
        item_path=ItemPathSpec(prefix="/api/v1/widgets", sample_id="1"),
    )
    manifest = ConsoleManifest(
        manifest_version=2,
        product_type=_SYNTHETIC_PRODUCT_TYPE,
        display_name="Waddle Farm",
        resources=(resource,),
    )
    return ProductManifestEntry(
        product_id=product_id, product_type=_SYNTHETIC_PRODUCT_TYPE, manifest=manifest
    )


class TestBuildProductGroupDirectly:
    """Unit-level: `build_product_group` alone, no Click dispatch involved."""

    def test_builds_a_group_named_after_the_product_type(self) -> None:
        """Builds a group named after the product type."""
        group = build_product_group(_SYNTHETIC_PRODUCT_TYPE, (_synthetic_entry(),))
        assert group.name == _SYNTHETIC_PRODUCT_TYPE

    def test_builds_a_resource_subgroup_with_list_and_get(self) -> None:
        """Builds a resource subgroup with list and get."""
        group = build_product_group(_SYNTHETIC_PRODUCT_TYPE, (_synthetic_entry(),))
        resource_group = group.get_command(click.Context(group), _SYNTHETIC_RESOURCE_KIND)
        assert resource_group is not None
        assert isinstance(resource_group, click.Group)
        ctx = click.Context(resource_group)
        assert resource_group.get_command(ctx, "list") is not None
        assert resource_group.get_command(ctx, "get") is not None

    def test_resource_with_no_list_or_item_path_is_not_exposed(self) -> None:
        """Resource with no list or item path is not exposed."""
        entry = _synthetic_entry()
        no_read_resource = ResourceDescriptor(
            kind="unreadable",
            label="Unreadable",
            plural_label="Unreadables",
            id_field="id",
            name_field="name",
            transport="proxy",
            columns=(),
            empty_state="",
            error_state="",
            list=None,
            item_path=None,
        )
        manifest = ConsoleManifest(
            manifest_version=2,
            product_type=entry.product_type,
            display_name=entry.manifest.display_name,
            resources=(*entry.manifest.resources, no_read_resource),
        )
        entry_with_extra = ProductManifestEntry(
            product_id=entry.product_id, product_type=entry.product_type, manifest=manifest
        )
        group = build_product_group(entry.product_type, (entry_with_extra,))
        assert group.get_command(click.Context(group), "unreadable") is None


class _FakeManifestBackedGroup(PcliGroup):
    """A `PcliGroup` whose manifest source is a fixed, in-test tuple -- no HTTP, no keyring.

    This is the seam the falsification test needs: production `PcliGroup`
    drives `ManifestProvider` (real HTTP + keyring) from `ctx.params`, but
    the CLAIM under test is narrower and prior to any of that -- "given
    THESE manifests, does the product/resource tree resolve correctly".
    Overriding only `_manifest_provider` keeps `list_commands`/
    `get_command` themselves completely unmodified from production code.
    """

    def __init__(
        self, *args: Any, entries: tuple[ProductManifestEntry, ...], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._fixed_entries = entries

    def _manifest_provider(self, ctx: click.Context) -> Any:
        fixed_entries = self._fixed_entries

        class _Fixed:
            served_from_stale_cache = False

            def entries(self) -> tuple[ProductManifestEntry, ...]:
                return fixed_entries

        return _Fixed()


def _build_test_cli(
    entries: tuple[ProductManifestEntry, ...],
    *,
    portal_url: str = "https://portal.example.com",
) -> click.Group:
    @click.command("noop")
    def noop() -> None:
        """A static command, to prove static + discovered coexist."""

    @click.group(cls=_FakeManifestBackedGroup, entries=entries, static_commands={"noop": noop})
    @click.pass_context
    def root(ctx: click.Context) -> None:
        """Root group under test -- hardcodes `AppState` rather than parsing --portal-url.

        The falsification test is about manifest-driven discovery, not
        `cli.py`'s own `ctx.params`/`resolve_app_state` plumbing (that
        ordering is covered directly by
        `tests/test_cli.py::test_root_help_does_not_require_portal_url`)
        -- this callback sets `ctx.obj` straight from a known-good config.
        """
        from pcli.config import AppState, build_config

        ctx.obj = AppState(config=build_config(portal_url=portal_url, output="json"))

    return root


class TestSyntheticProductDiscoveredThroughClick:
    """End-to-end through Click's own dispatch (`list_commands`/`get_command`)."""

    def test_synthetic_product_appears_in_list_commands(self) -> None:
        """Synthetic product appears in list commands."""
        cli_group = _build_test_cli((_synthetic_entry(),))
        ctx = click.Context(cli_group)
        names = cli_group.list_commands(ctx)
        assert _SYNTHETIC_PRODUCT_TYPE in names
        assert "noop" in names  # static commands still present alongside it

    def test_synthetic_product_resource_list_subcommand_resolves(self) -> None:
        """Synthetic product resource list subcommand resolves."""
        cli_group = _build_test_cli((_synthetic_entry(),))
        ctx = click.Context(cli_group)
        product_group = cli_group.get_command(ctx, _SYNTHETIC_PRODUCT_TYPE)
        assert isinstance(product_group, click.Group)
        resource_group = product_group.get_command(ctx, _SYNTHETIC_RESOURCE_KIND)
        assert isinstance(resource_group, click.Group)
        list_cmd = resource_group.get_command(ctx, "list")
        assert list_cmd is not None
        assert list_cmd.name == "list"

    def test_unknown_product_returns_none_not_an_error(self) -> None:
        """Unknown product returns none not an error."""
        cli_group = _build_test_cli((_synthetic_entry(),))
        ctx = click.Context(cli_group)
        assert cli_group.get_command(ctx, "does-not-exist") is None

    def test_synthetic_product_list_command_runs_end_to_end(
        self, fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The full falsification claim: `pcli waddle-farm widgets list` actually WORKS.

        Real Click dispatch (`CliRunner`), a mocked portal (`httpx.
        MockTransport`) standing in for the proxy call, and a real keyring-
        backed token -- the only thing "fake" here is the manifest source,
        which is exactly the seam this test exists to prove is sufficient.
        """
        monkeypatch.delenv("PCLI_TOKEN", raising=False)
        config = build_config(portal_url="https://portal.example.com", output="json")
        TokenStore(config.host_key).save(
            TokenSet(
                access_token="tok",  # noqa: S106
                refresh_token="rt",  # noqa: S106
                token_type="Bearer",  # noqa: S106
                expires_at=time.time() + 3600,
            )
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/products/55/proxy/api/v1/widgets/"
            return httpx.Response(
                200,
                json={"widgets": [{"id": "w-1", "owner_team": None}]},
            )

        # PortalClient builds its own httpx.AsyncClient; patch the module
        # constructor it calls so the leaf `list` command's real proxy_get
        # goes through the mock transport instead of real DNS/sockets.
        real_async_client = httpx.AsyncClient

        def factory(**kwargs: object) -> httpx.AsyncClient:
            kwargs.pop("transport", None)
            return real_async_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(httpx, "AsyncClient", factory)

        cli_group = _build_test_cli((_synthetic_entry(),))
        runner = CliRunner()
        result = runner.invoke(
            cli_group,
            [_SYNTHETIC_PRODUCT_TYPE, _SYNTHETIC_RESOURCE_KIND, "list"],
        )
        assert result.exit_code == 0, result.output
        assert '"id": "w-1"' in result.output
        # absent_as is JSON output, so the raw None survives -- table
        # rendering's absent_as behaviour is proven separately in
        # tests/render/test_cells.py and tests/test_output.py.
        assert '"owner_team": null' in result.output

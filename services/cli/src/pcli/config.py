"""CLI-wide configuration, resolved once per invocation from flags + env vars.

No hardcoded default portal host: every PenguinTech `.app`/`.cloud` domain
this deployment could point at is operator-chosen, and guessing wrong would
send a real login attempt (device_code, later a bearer token) to a host the
caller never asked for. `--portal-url`/`PCLI_PORTAL_URL` is therefore
mandatory, not defaulted -- see `resolve_portal_url`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .errors import ConfigurationError

#: Env var pcli reads for the portal's base URL, e.g. "https://portal.penguincloud.io".
ENV_PORTAL_URL: str = "PCLI_PORTAL_URL"

#: Env var pcli reads for a pre-issued bearer token -- headless/CI use.
#: Never written to disk; see pcli.auth.keyring_store.TokenStore.
ENV_TOKEN: str = "PCLI_TOKEN"  # noqa: S105 -- this is an env var NAME, not a credential value

DEFAULT_TIMEOUT_SECONDS: float = 30.0

#: The `--output` choices pcli accepts.
OUTPUT_FORMATS: tuple[str, ...] = ("table", "json", "yaml")


@dataclass(slots=True, frozen=True)
class CLIConfig:
    """Everything a command needs to reach the portal and shape its output.

    Frozen: built once per invocation from `cli.py`'s root group callback
    and never mutated afterwards -- a subcommand that needs a different
    output format builds a new CLIConfig via `dataclasses.replace` rather
    than reaching back into this one.
    """

    portal_url: str
    output: str = "table"
    query: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def host_key(self) -> str:
        """Cache-namespace / keyring-account key for this portal host.

        `urlparse(...).netloc` (e.g. "portal.penguincloud.io") rather than
        the full URL: the manifest cache path
        (`~/.config/pcli/manifests/{portal_host}/{tenant_id}.json`) and the
        keyring account name both key on host only, so switching between
        `http://` and `https://` against the same host (a local dev
        deployment, say) still hits the same cached credential/manifest
        rather than silently forking storage.
        """
        parsed = urlparse(self.portal_url)
        return parsed.netloc or self.portal_url


def resolve_portal_url(explicit: str | None) -> str:
    """Resolve the portal base URL from `--portal-url`, else PCLI_PORTAL_URL.

    Raises ConfigurationError (never guesses a default) if neither is set --
    see the module docstring.
    """
    if explicit:
        return explicit.rstrip("/")
    from_env = os.environ.get(ENV_PORTAL_URL)
    if from_env:
        return from_env.rstrip("/")
    raise ConfigurationError(
        "No portal URL configured. Pass --portal-url, or set "
        f"{ENV_PORTAL_URL}=https://your-portal-host."
    )


def build_config(
    *,
    portal_url: str | None,
    output: str = "table",
    query: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CLIConfig:
    """Build a `CLIConfig`, resolving the portal URL and validating `output`.

    No `--token`/token_override flag, deliberately: critical-rules.md's
    Token & Secret Hygiene table forbids passing a credential as a CLI
    argument (it lands in shell history and `ps`). The one supported
    non-keyring path is `PCLI_TOKEN` in the environment, read directly by
    `pcli.auth.keyring_store.TokenStore.load` -- never threaded through
    `CLIConfig`.
    """
    resolved_url = resolve_portal_url(portal_url)
    if output not in OUTPUT_FORMATS:
        raise ConfigurationError(
            f"Unknown --output {output!r}; must be one of {', '.join(OUTPUT_FORMATS)}."
        )
    return CLIConfig(
        portal_url=resolved_url,
        output=output,
        query=query,
        timeout=timeout,
    )


@dataclass(slots=True)
class AppState:
    """`ctx.obj` for the root Click group: this invocation's config + manifest provider.

    NOT frozen, deliberately: `manifest_provider` is filled in lazily, on
    first use, by `pcli.commands.resource_group.PcliGroup._manifest_provider`.

    Caching it here -- on the per-INVOCATION `ctx.obj` -- rather than as an
    attribute of the `PcliGroup` instance itself matters for a reason
    sharper than tidiness: `cli.py`'s module-level `cli` object is a
    SINGLETON `PcliGroup`, constructed once at import time and reused by
    every subsequent call in the same process (every test in this
    codebase's suite invokes that same singleton via `CliRunner`, and nothing
    stops a future embedder from calling `pcli.cli.cli()` more than once per
    process either). A provider cached on `self` would silently keep
    answering the FIRST invocation's manifest snapshot -- and, in a
    multi-connection product, the first invocation's connection set -- for
    every later call in that process, never re-fetching. Typed `object`
    rather than `ManifestProvider` to avoid a config.py <-> resource_group.py
    import cycle; `resource_group.py` casts it back on read.
    """

    config: CLIConfig
    manifest_provider: object | None = field(default=None, repr=False)

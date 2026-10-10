"""Platform-secure token persistence. NEVER a plaintext file.

client.md: "Store tokens in platform-secure storage only... NEVER use
plaintext files for token storage." `TokenStore` has exactly two backends:

1. The OS keyring (macOS Keychain / Windows Credential Manager / Secret
   Service on Linux), via the `keyring` package.
2. `PCLI_TOKEN` from the environment, for headless/CI use -- read, never
   written back to any storage.

A host with neither a usable keyring backend nor `PCLI_TOKEN` set refuses
outright (`KeyringUnavailableError`) rather than inventing a third,
insecure path -- that silent fallback is the exact anti-pattern client.md
forbids, and the whole reason this module exists as its own file rather
than a few inline `keyring.set_password` calls at each call site.
"""

from __future__ import annotations

import os

import keyring
import keyring.errors

from ..config import ENV_TOKEN
from ..errors import KeyringUnavailableError
from .tokens import TokenSet

#: `keyring`'s own namespace for grouping credentials by application --
#: paired with the portal host (see `CLIConfig.host_key`) as the account
#: name, so two different portal deployments never collide in one keyring.
SERVICE_NAME: str = "pcli"

#: The module path of keyring's built-in no-op backend, returned by
#: `keyring.get_keyring()` when no real backend is discoverable (headless
#: Linux with no Secret Service daemon, a minimal container image, etc).
#: Checked by exact module-name prefix, not `isinstance` against
#: `keyring.backend.KeyringBackend` -- every real backend is ALSO an
#: instance of that base class, so an isinstance check would never
#: distinguish "no backend" from "a real one".
_FAIL_BACKEND_MODULE_PREFIX: str = "keyring.backends.fail"


def _env_token() -> str | None:
    return os.environ.get(ENV_TOKEN)


def backend_available() -> bool:
    """True if `keyring.get_keyring()` resolved to a real, usable backend."""
    backend = keyring.get_keyring()
    return not type(backend).__module__.startswith(_FAIL_BACKEND_MODULE_PREFIX)


class TokenStore:
    """Load/save/clear the token set for one portal host.

    `account` should be `CLIConfig.host_key` (the portal's own hostname) --
    never the raw URL, so switching `http`/`https` against the same
    deployment does not fork storage.
    """

    def __init__(self, account: str) -> None:
        """Bind this store to one portal host's keyring account."""
        self._account = account

    def _require_backend(self) -> None:
        if not backend_available():
            raise KeyringUnavailableError(
                "No platform keyring backend is available (tried macOS "
                "Keychain / Windows Credential Manager / Secret Service), "
                "and PCLI_TOKEN is not set. Configure a keyring backend, "
                "or export PCLI_TOKEN=<token> for headless/CI use. Refusing "
                "to fall back to a plaintext file."
            )

    def load(self) -> TokenSet | None:
        """Return the stored token set, or None if there isn't one.

        `PCLI_TOKEN` takes priority when set: an env-provided token is
        treated as a fresh, non-persisted credential every invocation (it
        is never written to the keyring by `save`, and it is never subject
        to the keyring-backend-required check below), matching the
        headless/CI contract in the module docstring.
        """
        env_token = _env_token()
        if env_token:
            # infinite-ish expiry: a caller supplying PCLI_TOKEN owns its
            # lifecycle (mints a fresh one per CI run, typically) -- pcli
            # has no refresh_token to rotate it with, so treating it as
            # perpetually valid and letting the PORTAL reject an actually
            # expired one is more honest than pcli guessing an expiry.
            return TokenSet(
                access_token=env_token,
                refresh_token="",
                token_type="Bearer",  # noqa: S106 -- an auth SCHEME name, not a credential
                expires_at=float("inf"),
            )
        self._require_backend()
        raw = keyring.get_password(SERVICE_NAME, self._account)
        if raw is None:
            return None
        return TokenSet.from_json(raw)

    def save(self, tokens: TokenSet) -> None:
        """Persist `tokens` to the platform keyring.

        A no-op when `PCLI_TOKEN` is set -- an env-supplied credential is
        never written to disk/keyring, matching `load`'s priority.
        """
        if _env_token():
            return
        self._require_backend()
        keyring.set_password(SERVICE_NAME, self._account, tokens.to_json())

    def clear(self) -> None:
        """Remove the stored token set, if any. Used by `pcli logout`."""
        if _env_token():
            return
        self._require_backend()
        try:
            keyring.delete_password(SERVICE_NAME, self._account)
        except keyring.errors.PasswordDeleteError:
            # Nothing was stored -- logout on an already-logged-out host is
            # a no-op, not an error.
            pass

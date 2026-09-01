"""Credential resolution shared by every command: load -> refresh-if-needed -> use.

One place implements "Validate token expiry before each call; refresh or
re-auth as needed" (client.md) so no command re-derives its own refresh
logic, and no command can accidentally skip it.
"""

from __future__ import annotations

import httpx

from .api.client import API_PREFIX, PortalClient
from .auth.keyring_store import TokenStore
from .auth.tokens import TokenSet
from .config import CLIConfig
from .errors import AuthenticationRequiredError


async def _refresh(config: CLIConfig, tokens: TokenSet) -> TokenSet | None:
    """Attempt one refresh-token exchange. Returns None on any failure -- never raises.

    A refresh failure (revoked/expired refresh token, network error) is not
    itself fatal here; the caller decides what "no usable token" means
    (`AuthenticationRequiredError`, pointing at `pcli login`).
    """
    if not tokens.refresh_token:
        return None
    async with httpx.AsyncClient(base_url=config.portal_url, timeout=config.timeout) as http:
        try:
            response = await http.post(
                f"{API_PREFIX}/auth/refresh", json={"refresh_token": tokens.refresh_token}
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        body = response.json()
        return TokenSet.from_login_response(body, tenant=tokens.tenant)


async def ensure_valid_token(config: CLIConfig) -> TokenSet:
    """Load the stored token set, refreshing it if it is expired.

    Raises `AuthenticationRequiredError` when there is nothing stored, or
    what was stored could not be refreshed -- the one message every command
    shows for "you need to `pcli login`".
    """
    store = TokenStore(config.host_key)
    tokens = store.load()
    if tokens is None:
        raise AuthenticationRequiredError("Not logged in. Run `pcli login` first.")
    if not tokens.is_expired:
        return tokens
    refreshed = await _refresh(config, tokens)
    if refreshed is None:
        raise AuthenticationRequiredError(
            "Session expired and could not be refreshed. Run `pcli login` again."
        )
    store.save(refreshed)
    return refreshed


def build_portal_client(config: CLIConfig, tokens: TokenSet) -> PortalClient:
    """A `PortalClient` pre-configured with this session's auth header."""
    return PortalClient(
        base_url=config.portal_url,
        token=tokens.access_token,
        token_type=tokens.token_type,
        timeout=config.timeout,
    )


__all__ = [
    "AuthenticationRequiredError",
    "build_portal_client",
    "ensure_valid_token",
]

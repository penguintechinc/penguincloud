"""Gough service-account session: login, token cache, and refresh-on-401.

Gough does not accept a static API key. Every call needs a bearer token from
``POST /api/v1/auth/login`` (email + password), and that token expires in 30
minutes — so the connection's stored credential is a *login*, not a token,
and the adapter has to hold a short-lived derived one.

Why the derived context
=======================
:class:`~app.adapters.base.AdapterContext` is frozen and carries the stored
credential, which the shared transport injects verbatim. If the adapter left
``auth_type='bearer'`` with the service-account *password* as ``api_key``,
the transport would faithfully send the password as a bearer token on every
request. So the login call is made with authentication disabled
(``auth_type='none'``) and every subsequent call uses a
``dataclasses.replace`` copy carrying the issued access token.

The copy changes only the credential fields. ``base_url`` is untouched, so
the transport's origin pin still governs where the token can go — the derived
context cannot widen the blast radius of the original.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, replace
from typing import Final

from ...adapter_errors import UpstreamAuthError
from ..base import AdapterContext
from ..transport import Transport
from .responses import unwrap

__all__ = ["GoughSession", "LOGIN_PATH", "REFRESH_PATH", "clear_token_cache"]

LOGIN_PATH: Final[str] = "/api/v1/auth/login"
REFRESH_PATH: Final[str] = "/api/v1/auth/refresh"

#: Gough issues access tokens with a 30-minute life
#: (``generate_jwt_token(..., expires_in_minutes=30)``). The portal expires
#: its cached copy early so a token cannot lapse mid-flight between the
#: freshness check and the product receiving it.
TOKEN_TTL_SECONDS: Final[float] = 30 * 60
TOKEN_EXPIRY_MARGIN_SECONDS: Final[float] = 60.0


@dataclass(slots=True)
class _CachedToken:
    """One connection's access token and the refresh token that renews it."""

    access_token: str
    refresh_token: str
    expires_at: float

    def is_fresh(self, now: float) -> bool:
        """True while the token is safely usable."""
        return now < self.expires_at - TOKEN_EXPIRY_MARGIN_SECONDS


#: Cache keyed by (connection_id, credential fingerprint). The fingerprint is
#: included so re-credentialing a connection invalidates its cached token
#: implicitly: an operator who rotates the service-account password would
#: otherwise keep getting the old session until it expired on its own.
_TOKEN_CACHE: dict[tuple[int, str], _CachedToken] = {}

#: One lock PER CACHE KEY, so a burst of parallel calls for one connection
#: performs a single login while every other connection proceeds untouched.
#:
#: This was a single module-level ``asyncio.Lock`` held across the network
#: login. Because the await happened inside the critical section, one Gough
#: instance that was slow or hanging stalled EVERY Gough request in the
#: portal — including requests to entirely different tenants' connections,
#: which share nothing with it but this lock. The blast radius of one
#: unreachable product was every product of that type.
#:
#: The keys are the same ``(connection_id, credential fingerprint)`` pairs the
#: token cache uses, so contention is scoped exactly to the callers who would
#: otherwise duplicate the same login.
#:
#: This module is the template Phase-4N and 4T copy, which is why it is worth
#: fixing here rather than three times later.
_KEY_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}

#: Guards mutation of :data:`_KEY_LOCKS` itself. Held only long enough to hand
#: out a lock — never across a network call, which is the whole distinction
#: from the lock it replaced.
_LOCKS_GUARD = asyncio.Lock()


async def _lock_for(key: tuple[int, str]) -> asyncio.Lock:
    """Return the lock guarding one connection's cached token.

    Created on demand under :data:`_LOCKS_GUARD` so two coroutines racing for
    the same new key cannot each build a lock and then both proceed to log in
    — which would reintroduce the duplicate-login this exists to prevent.
    """
    async with _LOCKS_GUARD:
        lock = _KEY_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _KEY_LOCKS[key] = lock
        return lock


def _fingerprint(ctx: AdapterContext) -> str:
    """Non-reversible identifier for the credential currently configured.

    A hash rather than the credential itself: this value is a dict key held
    for the process lifetime, and a plaintext password living in a
    module-level map is a credential at rest in the portal's memory for no
    benefit.
    """
    digest = hashlib.sha256()
    digest.update(ctx.api_key.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(ctx.api_secret.encode("utf-8"))
    return digest.hexdigest()


def clear_token_cache() -> None:
    """Drop every cached token. For tests and connection teardown.

    Also drops the per-key locks. They are cheap, but keeping them after their
    token is gone would leave one entry per connection ever seen — the same
    unbounded-growth shape the token cache itself has (tracked as M13).
    """
    _TOKEN_CACHE.clear()
    _KEY_LOCKS.clear()


class GoughSession:
    """Obtains and renews the bearer token for one Gough connection."""

    def __init__(self, transport: Transport) -> None:
        """Bind the session to the shared transport."""
        self._transport = transport

    async def authorize(self, ctx: AdapterContext) -> AdapterContext:
        """Return a context carrying a valid Gough access token.

        Uses the cached token when it is still fresh, otherwise logs in.
        """
        key = (ctx.connection_id, _fingerprint(ctx))
        async with await _lock_for(key):
            cached = _TOKEN_CACHE.get(key)
            if cached is not None and cached.is_fresh(time.monotonic()):
                return self._with_token(ctx, cached.access_token)
            token = await self._login(ctx)
            _TOKEN_CACHE[key] = token
        return self._with_token(ctx, token.access_token)

    async def reauthorize(self, ctx: AdapterContext) -> AdapterContext:
        """Force a new token after the product rejected the cached one.

        Called on a 401 mid-request. Tries ``/auth/refresh`` with the stored
        refresh token first and falls back to a full login, because a refresh
        token can be revoked or expired independently of the access token —
        falling back means a revoked session self-heals instead of failing
        every request until the process restarts.
        """
        key = (ctx.connection_id, _fingerprint(ctx))
        async with await _lock_for(key):
            cached = _TOKEN_CACHE.pop(key, None)
            token: _CachedToken | None = None
            if cached is not None:
                token = await self._refresh(ctx, cached)
            if token is None:
                token = await self._login(ctx)
            _TOKEN_CACHE[key] = token
        return self._with_token(ctx, token.access_token)

    @staticmethod
    def _with_token(ctx: AdapterContext, access_token: str) -> AdapterContext:
        """Copy the context with the issued token as its bearer credential.

        ``api_secret`` is blanked: nothing downstream needs the service
        account's password once a token exists, and a copy that keeps
        carrying it is one more object a traceback can render.
        """
        return replace(ctx, auth_type="bearer", api_key=access_token, api_secret="")

    @staticmethod
    def _anonymous(ctx: AdapterContext) -> AdapterContext:
        """Copy the context with credential injection disabled.

        The login and refresh calls carry their credentials in the BODY. If
        the context still said ``bearer``, the transport would also attach the
        stored password as an ``Authorization`` header — sending the
        service-account password to an endpoint that never asked for it.
        """
        return replace(ctx, auth_type="none", api_key="", api_secret="")

    async def _login(self, ctx: AdapterContext) -> _CachedToken:
        """Exchange the stored service-account credential for tokens."""
        if not ctx.api_key or not ctx.api_secret:
            raise UpstreamAuthError(
                "Gough connection has no service-account credential configured; "
                "set the account email as the API key and its password as the "
                "API secret"
            )
        url = f"{ctx.base_url.rstrip('/')}{LOGIN_PATH}"
        response = await self._transport.request(
            "POST",
            url,
            self._anonymous(ctx),
            json={"email": ctx.api_key, "password": ctx.api_secret},
        )
        payload = unwrap(response, "gough login").dict_data()
        access = payload.get("access_token")
        if not isinstance(access, str) or not access:
            raise UpstreamAuthError("Gough login returned no access_token")
        refresh = payload.get("refresh_token")
        return _CachedToken(
            access_token=access,
            refresh_token=refresh if isinstance(refresh, str) else "",
            expires_at=time.monotonic() + TOKEN_TTL_SECONDS,
        )

    async def _refresh(self, ctx: AdapterContext, cached: _CachedToken) -> _CachedToken | None:
        """Renew the access token, or return None to fall back to login.

        Returns None rather than raising on any failure: refresh is an
        optimisation over logging in again, so a failure here should cost one
        extra request, never the whole call.
        """
        if not cached.refresh_token:
            return None
        url = f"{ctx.base_url.rstrip('/')}{REFRESH_PATH}"
        try:
            response = await self._transport.request(
                "POST",
                url,
                self._anonymous(ctx),
                json={"refresh_token": cached.refresh_token},
            )
            payload = unwrap(response, "gough token refresh").dict_data()
        except Exception:
            return None
        access = payload.get("access_token")
        if not isinstance(access, str) or not access:
            return None
        return _CachedToken(
            access_token=access,
            refresh_token=cached.refresh_token,
            expires_at=time.monotonic() + TOKEN_TTL_SECONDS,
        )

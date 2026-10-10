"""Decode Tobogganing responses and map its statuses onto the shared taxonomy.

Tobogganing's error envelope is a single ``{"error": "..."}`` key — flatter than
Nest's ``code``/``message`` pair — and it is emitted by every handler including
the ones that answer through ``jsonify``.

Why 401 AND 403 both become UpstreamAuthError
=============================================
Tobogganing rejects a bad credential with **either** status depending on which
middleware refused it, and both mean the same thing to the portal:

* ``403`` from ``@require_tenant`` / ``@require_scope`` — the stored token was
  missing, unparseable, carried no ``tenant`` claim, or lacked a scope
  (``hub_api/auth/middleware.py:118-133``, ``:160-186``).
* ``401`` from ``@require_machine_jwt`` — wrong audience or unknown token
  (``:563-568``, ``:601``).

Neither is a statement about the portal caller's own authorization, so both
raise :class:`~app.adapter_errors.UpstreamAuthError` (502) rather than a 401 that
would tell the browser to re-login and fix nothing. A 403 here is emphatically
NOT "this operator may not do that" — the portal already enforced that with
``@require_scope`` before the adapter was reached.

``402`` is Tobogganing-specific: ``@require_feature`` answers it when a module
is disabled by licence or feature flag. It maps to
:class:`~app.adapter_errors.AdapterCapabilityError` so the UI can say "not
enabled on this deployment" rather than "forbidden", which would send an
operator to check permissions that are fine.
"""

from __future__ import annotations

import json
from typing import Any, Final

import httpx

from ...adapter_errors import (
    AdapterCapabilityError,
    RateLimitedError,
    ResourceConflictError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamValidationError,
)

__all__ = ["TobogganingResponse", "unwrap", "raise_for_status"]

#: Tobogganing's uniform metadata sidecar, present on most (not all) handlers.
_META_KEY: Final[str] = "meta"

#: Tobogganing's error envelope key — one flat string, not a code/message pair.
_ERROR_KEY: Final[str] = "error"


class TobogganingResponse:
    """A decoded Tobogganing response body, collection envelope or bare object.

    ``data`` is what the caller asked for and ``meta`` is the envelope's
    metadata (empty when the handler emits none — SASE's block-page handlers
    return a bare ``{"pages": [...]}`` with no ``meta`` at all, while SD-WAN's
    include one).
    """

    __slots__ = ("data", "meta", "status_code", "headers")

    def __init__(
        self,
        data: Any,
        meta: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Store the decoded payload, its metadata and response detail."""
        self.data = data
        self.meta = meta
        self.status_code = status_code
        self.headers = headers or {}

    def dict_data(self) -> dict[str, Any]:
        """Return the payload as a mapping, or raise if it is not one."""
        if not isinstance(self.data, dict):
            raise UpstreamError("tobogganing returned a non-object where one was required")
        return self.data

    def items(self, key: str) -> list[dict[str, Any]]:
        """Return the collection's rows from under ``key``, or raise.

        ``key`` is that collection's own envelope key — Tobogganing has no
        shared one and never uses ``items`` for anything, so there is nothing
        to default to. See :mod:`app.adapters.tobogganing.mapping`.

        **An absent key raises rather than returning an empty list.** Every
        Tobogganing list handler builds its key unconditionally from a list
        comprehension, so an empty collection still arrives as
        ``{"peers": []}``. A missing key therefore means the response is not
        the shape this adapter was written against, and the only reading a
        caller can give an empty list is the factual "there are none" — which
        is exactly how Phase 4N left three of Nest's four kinds rendering as
        permanently empty behind a screen that stated it as fact.
        """
        data = self.data
        if not isinstance(data, dict):
            raise UpstreamError(
                f"tobogganing returned {type(data).__name__} where a collection "
                f"envelope carrying {key!r} was expected"
            )
        if key not in data:
            raise UpstreamError(
                f"tobogganing returned a collection with no {key!r} key "
                f"(got {sorted(data)!r}) — refusing to report it as empty"
            )
        raw = data[key]
        if not isinstance(raw, list):
            raise UpstreamError(f"tobogganing returned a non-list under {key!r}")
        return [item for item in raw if isinstance(item, dict)]


def _decode(response: httpx.Response) -> Any:
    """Decode a JSON body, tolerating an empty one."""
    if not response.content:
        return None
    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _error_detail(payload: Any, fallback: str) -> str:
    """Build an error message from Tobogganing's flat error envelope."""
    if not isinstance(payload, dict):
        return fallback
    message = payload.get(_ERROR_KEY)
    return str(message) if message else fallback


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Map a non-2xx Tobogganing response onto the shared error taxonomy.

    See the module docstring for why 401 and 403 collapse together, and why
    402 is a capability error rather than an authorization one.
    """
    status = response.status_code
    if status < 400:
        return

    payload = _decode(response)
    detail = _error_detail(payload, f"tobogganing returned {status}")
    message = f"{context}: {detail}"

    if status in (400, 422):
        raise UpstreamValidationError(message)
    if status in (401, 403):
        raise UpstreamAuthError(message)
    if status == 402:
        raise AdapterCapabilityError(message)
    if status == 404:
        raise ResourceNotFoundError(message)
    if status == 409:
        raise ResourceConflictError(message)
    if status == 429:
        retry_after = response.headers.get("retry-after")
        try:
            seconds = float(retry_after) if retry_after else None
        except ValueError:
            seconds = None
        raise RateLimitedError(message, retry_after=seconds)
    raise UpstreamError(message)


def unwrap(response: httpx.Response, context: str) -> TobogganingResponse:
    """Decode a Tobogganing response, raising the mapped error for a non-2xx."""
    raise_for_status(response, context)
    payload = _decode(response)
    meta: dict[str, Any] = {}
    if isinstance(payload, dict):
        raw_meta = payload.get(_META_KEY)
        if isinstance(raw_meta, dict):
            meta = raw_meta
    return TobogganingResponse(
        data=payload,
        meta=meta,
        status_code=response.status_code,
        headers={key.lower(): value for key, value in response.headers.items()},
    )

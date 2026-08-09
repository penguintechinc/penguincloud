"""Nest response decoding and status-to-taxonomy mapping.

Nest answers in two shapes and one error envelope, and this module is the
only place that difference is handled so no call site has to remember which
family an endpoint belongs to.

Collections answer ``{"items": [...], "meta": {"count": N, "version": 1}}``
(``apps/api/handlers/dataresource.py:47``); single resources answer the bare
object. Errors — at every status — answer a consistent envelope::

    {"code": "nest.dataresource.not_found", "message": "...",
     "requestId": "...", "docsUrl": "..."}

``code`` is the field worth surfacing: it is stable and machine-readable,
whereas ``message`` is prose. It is carried into the raised
:class:`~app.adapters.base.AdapterError` message so an operator reading a
portal error can search Nest's docs for the same string.
"""

from __future__ import annotations

import json
from typing import Any, Final

import httpx

from ..base import (
    RateLimitedError,
    ResourceConflictError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamValidationError,
)

__all__ = ["NestResponse", "unwrap", "raise_for_status"]

#: Nest's collection envelope keys.
_ITEMS_KEY: Final[str] = "items"
_META_KEY: Final[str] = "meta"

#: Nest's error envelope keys.
_CODE_KEY: Final[str] = "code"
_MESSAGE_KEY: Final[str] = "message"


class NestResponse:
    """A decoded Nest response body, collection envelope or bare object.

    ``data`` is what the caller asked for and ``meta`` is the envelope's
    metadata (empty for a bare object), so ``count`` lookups are uniform.
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
            raise UpstreamError("nest returned a non-object where one was required")
        return self.data

    def items(self) -> list[dict[str, Any]]:
        """Return the collection's items, or raise if the shape is wrong.

        An absent ``items`` key yields an empty list rather than an error:
        Nest omits it for a genuinely empty collection on some handlers, and
        treating that as a failure would render "no databases yet" as an
        outage.
        """
        data = self.data
        if isinstance(data, dict):
            raw = data.get(_ITEMS_KEY)
        else:
            raw = data
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise UpstreamError("nest returned a non-list collection")
        return [item for item in raw if isinstance(item, dict)]


def _decode(response: httpx.Response) -> Any:
    """Decode a JSON body, tolerating an empty one.

    A ``204`` (Nest's answer to every delete) has no body at all, and a
    failed decode there is not an upstream error.
    """
    if not response.content:
        return None
    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _error_detail(payload: Any, fallback: str) -> str:
    """Build an error message from Nest's error envelope."""
    if not isinstance(payload, dict):
        return fallback
    code = payload.get(_CODE_KEY)
    message = payload.get(_MESSAGE_KEY)
    if code and message:
        return f"{code}: {message}"
    if code:
        return str(code)
    if message:
        return str(message)
    return fallback


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Map a non-2xx Nest response onto the shared error taxonomy.

    ``401``/``403`` both mean the portal's STORED credential was refused —
    Nest checks the bearer token's scopes and, on tenant-scoped routes, that
    the token's ``tenant`` claim equals the tenant in the URL
    (``handlers/cost.py:48-58``). Neither is a statement about the portal
    caller's own authorization, so both raise
    :class:`~app.adapters.base.UpstreamAuthError` (502) rather than a 401
    that would tell the browser to re-login and fix nothing.
    """
    status = response.status_code
    if status < 400:
        return

    payload = _decode(response)
    detail = _error_detail(payload, f"nest returned {status}")
    message = f"{context}: {detail}"

    if status in (400, 422):
        raise UpstreamValidationError(message)
    if status in (401, 403):
        raise UpstreamAuthError(message)
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


def unwrap(response: httpx.Response, context: str) -> NestResponse:
    """Decode a Nest response, raising the mapped error for a non-2xx."""
    raise_for_status(response, context)
    payload = _decode(response)
    meta: dict[str, Any] = {}
    if isinstance(payload, dict):
        raw_meta = payload.get(_META_KEY)
        if isinstance(raw_meta, dict):
            meta = raw_meta
    return NestResponse(
        data=payload,
        meta=meta,
        status_code=response.status_code,
        headers={key.lower(): value for key, value in response.headers.items()},
    )

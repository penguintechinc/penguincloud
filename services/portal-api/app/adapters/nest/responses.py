"""Nest response decoding and status-to-taxonomy mapping.

Collections
===========
**Nest has no single collection envelope.** Each collection names its own key
and only data-resources uses ``items``:

===========================  ===============  =============================
collection                   key              handler
===========================  ===============  =============================
``data-resources``           ``items``        ``dataresource.py:47``
``snapshots``                ``snapshots``    ``protection.py:26``
``protection-policies``      ``policies``     ``protection.py:206``
``search-pools``             ``searchPools``  ``searchpool.py:25``
===========================  ===============  =============================

``meta`` (``{"count": N, "version": 1}``) is the one part that is uniform.
Single resources answer the bare object with no envelope at all.

The caller therefore passes the key it expects
(:data:`~.mapping.COLLECTION_ENVELOPE_KEYS`), and an absent key is an error
rather than an empty list — see :meth:`NestResponse.items`.

Errors
======
Every non-2xx answers an envelope of the form::

    {"code": "nest.dataresource.not_found", "message": "...",
     "requestId": "..."}

``code``, ``message`` and ``requestId`` are present throughout. ``docsUrl`` is
added by *some* handlers only — the auth, not-found and cost paths
(``apps/api/app.py:108``, ``:206``, ``handlers/cost.py:69``) — and is absent
from the generic ``nest.internal`` 500s, so nothing here depends on it.

``code`` is the field worth surfacing: it is stable and machine-readable,
whereas ``message`` is prose. It is carried into the raised
:class:`~app.adapter_errors.AdapterError` message so an operator reading a
portal error can search Nest's docs for the same string.
"""

from __future__ import annotations

import json
from typing import Any, Final

import httpx

from ...adapter_errors import (
    RateLimitedError,
    ResourceConflictError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamValidationError,
)

__all__ = ["NestResponse", "unwrap", "raise_for_status"]

#: The one envelope key that IS uniform across Nest's collections.
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

    def items(self, key: str) -> list[dict[str, Any]]:
        """Return the collection's rows from under ``key``, or raise.

        ``key`` is the collection's own envelope key — see the module
        docstring; there is no shared one to default to.

        **An absent key raises rather than returning an empty list.** Every
        Nest list handler builds its key unconditionally
        (``[x.to_dict() for x in ...]``), so an empty collection still arrives
        as ``{"snapshots": []}``: a missing key means the response is not the
        shape this adapter was written against, and the only reading a caller
        can give an empty list is the factual "there are none". That fallback
        is what let three of four kinds decode as permanently empty behind a
        screen that stated it as fact.
        """
        data = self.data
        if not isinstance(data, dict):
            raise UpstreamError(
                f"nest returned {type(data).__name__} where a collection "
                f"envelope carrying {key!r} was expected"
            )
        if key not in data:
            raise UpstreamError(
                f"nest returned a collection with no {key!r} key "
                f"(got {sorted(data)!r}) — refusing to report it as empty"
            )
        raw = data[key]
        if not isinstance(raw, list):
            raise UpstreamError(f"nest returned a non-list under {key!r}")
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
    :class:`~app.adapter_errors.UpstreamAuthError` (502) rather than a 401
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

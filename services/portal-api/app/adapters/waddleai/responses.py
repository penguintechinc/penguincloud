"""Decode WaddleAI responses and map its statuses onto the shared taxonomy.

WaddleAI's error envelope is a single ``{"error": "..."}`` key — verified
against ``services/management/app/api/v1/auth.py``'s ``require_auth`` /
``require_scope`` decorators and every handler's own ``jsonify({"error":
...})`` calls in ``providers.py``/``knowledge.py``/``quotas.py``. Flat, like
Tobogganing's, not the ``code``/``message`` pair Nest and Gough use.

Why 401 AND 403 both become UpstreamAuthError
===============================================
Unlike Tobogganing (two auth planes), WaddleAI has exactly one:
``require_auth`` answers 401 for a missing/invalid/expired bearer token,
and ``require_scope`` answers 403 when the token is valid but lacks the
required ``Permission`` (``auth.py:225``, ``:247``, ``:273``, ``:278-279``).
Both describe the STORED connection credential's own standing with
WaddleAI, never the portal caller's authorization — the portal already
enforced that with its own ``@require_scope`` before the adapter was
reached. So both raise :class:`~app.adapter_errors.UpstreamAuthError` (502)
rather than a 401 that would tell the browser to re-login and fix nothing,
matching the precedent set in
:mod:`app.adapters.tobogganing.responses`.

A 404 from the knowledge routes can mean "feature disabled"
=============================================================
``knowledge.py``'s ``_knowledge_ingest_enabled`` gate answers plain ``404
{"error": "knowledge_ingest feature disabled"}`` when the
``waddleai.knowledge_ingest`` flag is off for the caller's org — WaddleAI has
no 402-style capability status the way Tobogganing's ``@require_feature``
does. Rather than special-case that string, this module maps every 404 to
:class:`~app.adapter_errors.ResourceNotFoundError` uniformly and lets the
included message speak for itself (``"{context}: {detail}"``) — inspecting
response bodies to reclassify a status code is exactly the kind of
string-matching fragility the adapter contract avoids elsewhere.
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

__all__ = ["WaddleAIResponse", "unwrap", "raise_for_status"]

#: WaddleAI's error envelope key — one flat string, matching every handler's
#: own ``jsonify({"error": ...})`` call.
_ERROR_KEY: Final[str] = "error"


class WaddleAIResponse:
    """A decoded WaddleAI response body — a collection envelope or a bare object."""

    __slots__ = ("data", "status_code", "headers")

    def __init__(
        self,
        data: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Store the decoded payload and response detail."""
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}

    def items(self, key: str) -> list[dict[str, Any]]:
        """Return the collection's rows from under ``key``, or raise.

        **An absent key raises rather than returning an empty list** — see
        :mod:`app.adapters.tobogganing.responses`'s identical method for why:
        every WaddleAI list handler here builds its key unconditionally
        (``jsonify({"providers": result, "total": ...})`` etc.), so an empty
        collection still arrives as ``{"providers": []}``. A missing key
        means the response is not the shape this adapter was written
        against.
        """
        data = self.data
        if not isinstance(data, dict):
            raise UpstreamError(
                f"waddleai returned {type(data).__name__} where a collection "
                f"envelope carrying {key!r} was expected"
            )
        if key not in data:
            raise UpstreamError(
                f"waddleai returned a collection with no {key!r} key "
                f"(got {sorted(data)!r}) — refusing to report it as empty"
            )
        raw = data[key]
        if not isinstance(raw, list):
            raise UpstreamError(f"waddleai returned a non-list under {key!r}")
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
    """Build an error message from WaddleAI's flat error envelope."""
    if not isinstance(payload, dict):
        return fallback
    message = payload.get(_ERROR_KEY)
    return str(message) if message else fallback


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Map a non-2xx WaddleAI response onto the shared error taxonomy.

    See the module docstring for why 401 and 403 collapse together, and why
    404 is not string-matched for the feature-disabled case.
    """
    status = response.status_code
    if status < 400:
        return

    payload = _decode(response)
    detail = _error_detail(payload, f"waddleai returned {status}")
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


def unwrap(response: httpx.Response, context: str) -> WaddleAIResponse:
    """Decode a WaddleAI response, raising the mapped error for a non-2xx."""
    raise_for_status(response, context)
    payload = _decode(response)
    return WaddleAIResponse(
        data=payload,
        status_code=response.status_code,
        headers={key.lower(): value for key, value in response.headers.items()},
    )

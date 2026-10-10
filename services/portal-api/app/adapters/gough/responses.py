"""Gough response unwrapping and status-to-taxonomy mapping.

Gough does not speak one response shape, and pretending otherwise is the
first bug an integrator writes. Its ``_helpers.envelope_success`` routes
(nodes, biomes, deployments, clusters) answer::

    {"status": "success", "data": {...}, "meta": {"next_cursor": ...}}

while its older handlers (``/api/v1/agents``, ``/api/v1/auth/*``,
``/api/v1/status``, ``/healthz``) answer a bare object with no envelope at
all. :func:`unwrap` accepts both and is the only place that difference is
handled, so no call site has to remember which family an endpoint belongs
to — and adding an endpoint of the wrong family cannot silently yield
``None`` at a caller expecting data.
"""

from __future__ import annotations

import json
from typing import Any, Final

import httpx

from ...adapter_errors import (
    AdapterError,
    RateLimitedError,
    ResourceConflictError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamValidationError,
)

__all__ = ["GoughResponse", "unwrap", "raise_for_status"]

#: Gough's own field name for the opaque cursor, inside ``meta``.
_META_CURSOR: Final[str] = "next_cursor"


class GoughResponse:
    """A decoded Gough response body, envelope or bare.

    ``data`` is what the caller wanted; ``meta`` is the envelope's metadata or
    an empty mapping for a bare response, so ``next_cursor`` lookups are
    uniform.
    """

    __slots__ = ("data", "meta")

    def __init__(self, data: Any, meta: dict[str, Any]) -> None:
        """Store the decoded payload and its metadata."""
        self.data = data
        self.meta = meta

    @property
    def next_cursor(self) -> str | None:
        """The opaque cursor for the following page, when Gough sent one.

        Gough emits ``next_cursor: null`` on the last page rather than
        omitting the key, so an explicit ``or None`` keeps "last page" and
        "not a cursor paginator" indistinguishable to the caller — which is
        correct, because both mean "do not ask for more".
        """
        value = self.meta.get(_META_CURSOR)
        return str(value) if value else None

    def dict_data(self) -> dict[str, Any]:
        """Return ``data`` as a mapping, or raise if Gough sent something else.

        Every endpoint this adapter calls returns an object. A list or scalar
        here means the route changed shape underneath us, and failing loudly
        beats a ``.get()`` on a list raising ``AttributeError`` three frames
        away.
        """
        if not isinstance(self.data, dict):
            raise UpstreamError(
                f"expected a JSON object from Gough, got {type(self.data).__name__}"
            )
        return self.data


def _decode(response: httpx.Response) -> Any:
    """Decode a JSON body, or raise UpstreamError describing what arrived.

    A product that answers 200 with an HTML error page is a real failure mode
    (a reverse proxy in front of it, a login redirect page). Letting
    ``json.JSONDecodeError`` escape would surface it as a portal crash rather
    than an upstream fault.
    """
    if not response.content:
        return {}
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        content_type = response.headers.get("content-type", "unknown")
        raise UpstreamError(
            f"Gough returned a non-JSON body (content-type: {content_type})"
        ) from exc


def _error_message(body: Any, fallback: str) -> tuple[str, list[dict[str, Any]]]:
    """Pull a human message and any field violations out of a Gough error.

    Handles the enveloped form (``error.message`` + ``error.details``) and the
    bare form (``{"error": "..."}``) used by the auth and agent handlers.
    """
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or fallback)
            details = error.get("details")
            violations = []
            if isinstance(details, dict):
                raw = details.get("violations")
                if isinstance(raw, list):
                    violations = [v for v in raw if isinstance(v, dict)]
            return message, violations
        if isinstance(error, str) and error:
            return error, []
    return fallback, []


def _retry_after(response: httpx.Response) -> float | None:
    """Parse ``Retry-After`` seconds, ignoring the HTTP-date form.

    A date-formatted value is legal but Gough does not emit one; treating an
    unparseable header as absent is safer than guessing a delay.
    """
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Translate a Gough error status into the shared taxonomy.

    ``context`` names the operation, so an error surfaced three layers up
    still says which call produced it.

    401/403 become :class:`UpstreamAuthError` rather than propagating as the
    portal caller's own 401: the credential that was rejected is the *stored
    service-account credential*, and telling the browser to re-login fixes
    nothing. The caller who can fix it is an operator re-credentialing the
    connection, which is what a 502 plus this message says.
    """
    status = response.status_code
    if status < 400:
        return

    body = None
    try:
        body = _decode(response)
    except UpstreamError:
        body = None

    message, violations = _error_message(body, f"Gough returned HTTP {status}")
    detail = f"{context}: {message}"

    error: AdapterError
    if status in (401, 403):
        error = UpstreamAuthError(detail)
    elif status == 404:
        error = ResourceNotFoundError(detail)
    elif status == 409:
        error = ResourceConflictError(detail)
    elif status == 429:
        error = RateLimitedError(detail, retry_after=_retry_after(response))
    elif status in (400, 422):
        error = UpstreamValidationError(detail, violations=violations)
    else:
        error = UpstreamError(detail)
    raise error


def unwrap(response: httpx.Response, context: str) -> GoughResponse:
    """Check the status, then decode either response shape.

    Raises one of the shared taxonomy errors for any 4xx/5xx; see
    :func:`raise_for_status`.
    """
    raise_for_status(response, context)
    body = _decode(response)

    if isinstance(body, dict) and body.get("status") == "success":
        meta = body.get("meta")
        return GoughResponse(
            data=body.get("data"),
            meta=meta if isinstance(meta, dict) else {},
        )

    # An enveloped error with a 2xx status. Gough should not do this, but a
    # body that says "error" is not success no matter what the status line
    # claims, and treating it as data would hand the caller an error object
    # shaped like a resource.
    if isinstance(body, dict) and body.get("status") == "error":
        message, _ = _error_message(body, "Gough reported an error")
        raise UpstreamError(f"{context}: {message}")

    return GoughResponse(data=body, meta={})

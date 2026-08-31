"""Adapter error taxonomy and the upstream-response marker header.

Both pieces here are genuinely cross-cutting: every adapter raises one of
these on failure, and every route/health module that calls an adapter needs
to catch ``AdapterError`` and mark its response with
``UPSTREAM_RESPONSE_HEADER`` when the body came from (or was built from) the
product's own reply. Neither piece has any adapter-specific knowledge — no
``Adapter`` Protocol, no ``RouteRule``, no transport concern — so keeping
them in :mod:`app.adapters.base` made every route/health importer that only
wanted the error taxonomy look like it was reaching into the proxy/adapters
layer, when what it actually needed was floor-level shared vocabulary.
:mod:`app.adapters.base` re-exports both for backward compatibility and
still uses ``AdapterCapabilityError`` internally (``HealthOnlyAdapter``).

This module must import nothing from ``app.adapters``, ``app.licensing``,
``app.tenancy``, or any route module — same constraint as :mod:`app.rbac`,
and for the same reason: it is depended on from every layer, so it cannot
depend back on any of them.
"""

from __future__ import annotations

from typing import Any, Final


class AdapterError(Exception):
    """Base for every failure an adapter is allowed to surface.

    Phase 4 adapters raise one of the subclasses below rather than letting an
    ``httpx.HTTPStatusError`` escape: a raw transport exception carries the
    product's URL and headers into the portal's error path, and forces every
    caller to re-derive what a given upstream status means.
    """


class AdapterCapabilityError(AdapterError):
    """Raised when an adapter does not support a requested operation."""


class ResourceNotFoundError(AdapterError):
    """The product does not have the requested resource.

    Distinct from :class:`AdapterCapabilityError`: "this portal cannot list
    widgets" and "this product has no widget 7" are different answers, and
    collapsing them makes a missing integration look like an empty account.
    """


class ResourceConflictError(AdapterError):
    """The product refused the write as conflicting with current state.

    Duplicate unique key, edit against a stale version, delete of something
    still referenced. Retrying is pointless; the caller must re-read.
    """


class RateLimitedError(AdapterError):
    """The product is rate-limiting the portal.

    ``retry_after`` is seconds, taken from the product's header when it sent
    one. Kept as its own class so callers can back off instead of treating a
    throttle as an outage.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Record the message and the product's advertised retry delay."""
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamValidationError(AdapterError):
    """The product rejected the payload as invalid, field by field.

    Distinct from :class:`ResourceConflictError`, which is a disagreement with
    *current state* and tells the caller to re-read. This is a disagreement
    with the *payload*: re-reading changes nothing, the user must edit what
    they typed.

    It exists because the alternative was rendering Gough's 422
    ``validation_failed`` envelope as 502, which tells an operator the product
    is broken when in fact a form field is wrong — and hides the one piece of
    information that would fix it. ``violations`` carries the product's own
    per-field detail so a form can mark the offending inputs instead of
    showing a single opaque banner.
    """

    def __init__(self, message: str, violations: list[dict[str, Any]] | None = None) -> None:
        """Record the message and the product's per-field violations."""
        super().__init__(message)
        self.violations = violations or []


class UpstreamAuthError(AdapterError):
    """The product rejected the portal's *stored* credential.

    Never a statement about the portal caller's own authorization — it means
    the connection needs re-credentialing by an operator. Surfacing it as 401
    would tell the browser to re-login, which fixes nothing.
    """


class UpstreamError(AdapterError):
    """The product failed in a way with no more specific meaning."""


#: How each taxonomy member renders at the portal's API boundary. Defined
#: once so three Phase-4 adapters cannot each invent their own mapping.
_ERROR_STATUS: Final[tuple[tuple[type[AdapterError], int], ...]] = (
    (AdapterCapabilityError, 501),
    (ResourceNotFoundError, 404),
    (ResourceConflictError, 409),
    (UpstreamValidationError, 422),
    (RateLimitedError, 429),
    (UpstreamAuthError, 502),
    (UpstreamError, 502),
)


def adapter_error_status(exc: AdapterError) -> int:
    """Map an adapter error onto the HTTP status the portal should return.

    Falls back to 502 for an ``AdapterError`` subclass added without a
    mapping: an unrecognised adapter failure is still an upstream failure,
    never a 200 and never a 500 blamed on the portal.
    """
    for error_type, status in _ERROR_STATUS:
        if isinstance(exc, error_type):
            return status
    return 502


#: Set (to "true") on every response whose body was forwarded from, or built
#: from, a connected product's own reply — never on a portal-generated body.
#: The webui client (`lib/mutationError.ts`) trusts this header to decide
#: whether a body is safe to show an operator verbatim: unmarked is assumed
#: portal-native and shown as-is, marked is always replaced with a generic
#: message regardless of content.
#:
#: This is the definition to update FIRST when adding a fifth writer, and
#: the list below is deliberately exhaustive rather than "see the proxy" —
#: the original version of this constant named only ``app.proxy`` as owning
#: it, and that framing is what let ``app.product_access.adapter_failure``
#: ship unmarked in the same round: a reader who trusted "the proxy is the
#: one path" had no reason to go looking for a second one. Grep this
#: constant's name for the current, authoritative list of writers; the four
#: below are current as of this writing, not a promise the list stops here:
#:
#: - ``app.proxy`` — the raw forwarding path, sets it on the response built
#:   directly from ``outbound_response.content``.
#: - ``app.product_access.adapter_failure`` — every ``AdapterError`` message
#:   reaching it was built by a product adapter's own ``raise_for_status``
#:   (see e.g. ``adapters/nest/responses.py``), which interpolates the
#:   product's OWN response body into ``f"{context}: {detail}"``. That
#:   response never touches ``app.proxy`` at all — it is the "trusted,
#:   typed adapter method" path this module's own docstring describes above
#:   — so nothing else marks it. Every ``AdapterError`` subclass is treated
#:   identically, including ``AdapterCapabilityError`` (portal-generated,
#:   never carries upstream text today): a false positive here just shows
#:   the generic message for a message that happened to be safe, which
#:   costs a little detail; a false negative is the regression this exists
#:   to close.
#: - ``app.products.test_product_connection`` (``POST
#:   /products/<id>/test``) — a LIVE call to the product
#:   (``adapter.health()``), returned in the 200 body rather than raised as
#:   an ``AdapterError``, so ``adapter_failure`` never sees it. Marked
#:   unconditionally, same reasoning as above.
#: - ``app.health_api.get_products_health`` (``GET /products/health``) —
#:   reads ``CachedHealth.error``, written by ``health_poller.py``'s sweep
#:   from the same ``Transport.health_check`` exception text. No webui
#:   screen reads this endpoint today (latent, not a live leak), marked
#:   anyway so it is not a second miss for whichever one does. Declares
#:   ``@validate_response`` for its 200, so it sets this header by
#:   returning a 3-tuple ``(model, status, headers)`` rather than a
#:   pre-built ``Response`` — see the comment at that call site for why
#:   returning a ``Response`` there raises ``ResponseHeadersValidationError``
#:   instead of working.
#:
#: ``Operation.error`` and ``OperationLogLine.message`` (in
#: :mod:`app.adapters.base`) are a deliberate NON-writer: those fields are
#: verbatim-by-contract, not upstream-marked, by design — see their own
#: docstrings.
UPSTREAM_RESPONSE_HEADER: Final[str] = "X-Portal-Upstream-Response"

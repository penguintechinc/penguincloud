"""Process exit-code taxonomy.

Mirrors ``app.adapter_errors``' HTTP status taxonomy
(``services/portal-api/app/adapter_errors.py``) at one remove: pcli
receives the portal's own status/error family over HTTP and re-expresses it
as a process exit code, since that is the only signal a shell script
consuming pcli's output can branch on. Deliberately NOT a 1:1 copy of HTTP
status numbers -- an exit code is a small, script-friendly vocabulary, not
a second transport-status encoding.
"""

from __future__ import annotations

from typing import Final

EXIT_OK: Final[int] = 0
#: Uncategorized failure -- network error, unexpected response shape,
#: anything not mapped below.
EXIT_GENERAL: Final[int] = 1
#: No/expired/invalid credentials (HTTP 401). Distinct from FORBIDDEN: the
#: caller should run `pcli login`, not request a different scope.
EXIT_UNAUTHENTICATED: Final[int] = 2
#: Authenticated but not authorized for this call (HTTP 403).
EXIT_FORBIDDEN: Final[int] = 3
#: The requested resource does not exist (HTTP 404).
EXIT_NOT_FOUND: Final[int] = 4
#: The product refused a write as conflicting with current state (HTTP 409).
EXIT_CONFLICT: Final[int] = 9
#: The payload was rejected field-by-field (HTTP 422) -- re-reading changes
#: nothing, the caller must fix what they sent.
EXIT_VALIDATION: Final[int] = 22
#: Rate-limited by the portal or a connected product (HTTP 429).
EXIT_RATE_LIMITED: Final[int] = 29
#: A connected product failed, or the portal has no capability for the
#: requested operation (HTTP 501/502/503) -- not a pcli or portal defect.
EXIT_UPSTREAM: Final[int] = 52
#: Bad local configuration -- no portal URL, no auth backend available.
#: Matches BSD sysexits' EX_USAGE family loosely; not the same table, just
#: the same neighbourhood, since pcli is not a sysexits-conformant program.
EXIT_CONFIG: Final[int] = 64

#: HTTP status -> exit code. Any status not listed here falls back to
#: EXIT_GENERAL (see exit_code_for_status) -- an unrecognised status is
#: still a real failure, never treated as success.
_HTTP_STATUS_EXIT: Final[dict[int, int]] = {
    401: EXIT_UNAUTHENTICATED,
    403: EXIT_FORBIDDEN,
    404: EXIT_NOT_FOUND,
    409: EXIT_CONFLICT,
    422: EXIT_VALIDATION,
    429: EXIT_RATE_LIMITED,
    501: EXIT_UPSTREAM,
    502: EXIT_UPSTREAM,
    503: EXIT_UPSTREAM,
}


def exit_code_for_status(status_code: int) -> int:
    """Map one HTTP status code onto the exit code pcli should return for it."""
    return _HTTP_STATUS_EXIT.get(status_code, EXIT_GENERAL)

"""``--dev``: single-user evaluation mode, per general.md, implemented exactly.

What it is
==========
An undocumented flag on the portal entrypoint that unlocks every
Professional and Enterprise capability for a *single-user* evaluation or
internal development deployment. It unlocks **features only** — never
authentication, never authorization, never tenant isolation. Scope, tenant
and role checks run unchanged, and nothing in this module is reachable from
them.

Three conditions, all of them, continuously
===========================================
Active only when ALL hold, re-evaluated on every question asked of it:

1. the deployment domain is PenguinTech-controlled;
2. the identity table holds at most one user — counted server-side, from
   the database, never from a claim, header or client-supplied number;
3. the flag was actually passed.

Any one false makes it inert, silently. That is fail-closed by
construction: :func:`is_active` recomputes rather than reading a decision
made earlier.

**Nothing here may be latched at boot.** general.md calls a boolean fixed at
startup "a licensing hole", and it is the specific one this design exists to
avoid: an operator brings a deployment up with one user, premium features
unlock, then adds a team — and a latched flag keeps the whole paid feature
set on for an organisation that never bought it. The user count is therefore
queried per evaluation, and the second user is *refused* rather than
allowed-then-noticed.

"Undocumented" is not the control
=================================
The flag name is trivially discoverable. The domain check and the user cap
are the actual controls and are written to hold on their own; the flag being
absent from ``--help`` and from the OpenAPI document is tidiness, not
security.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Sequence
from typing import Any, Final

import structlog
from penguin_dal.quart_ext import get_db

from .licensing import configured_host, host_is_license_exempt

log = structlog.get_logger()

#: The flag itself. Deliberately absent from any argparse/--help surface.
DEV_FLAG: Final[str] = "--dev"

#: Maximum users while dev mode is active. The second is refused.
MAX_DEV_MODE_USERS: Final[int] = 1

#: The operator notice, verbatim from general.md. Printed to stderr — never
#: stdout — so it survives output being piped or parsed, and never
#: suppressible by any quiet flag.
DEV_MODE_NOTICE: Final[str] = (
    "╭──────────────────────────────────────────────────────────────────────╮\n"
    "│  DEVELOPMENT MODE (--dev) — ALL PREMIUM FEATURES UNLOCKED            │\n"
    "│                                                                      │\n"
    "│  For testing and evaluation only, limited to a single user.          │\n"
    "│  Use of this mode to obtain licensed functionality without a valid   │\n"
    "│  commercial license is a breach of the PenguinTech commercial        │\n"
    "│  license terms. See LICENSE.md.                                      │\n"
    "╰──────────────────────────────────────────────────────────────────────╯"
)

#: Whether the flag was passed. This is the ONLY piece of dev-mode state
#: that is remembered, and it records an input, not a decision — "the
#: operator asked for it", not "it is on".
_requested: bool = False

#: One-shot guard for the stderr notice, so a per-request evaluation does
#: not reprint the box on every call. It gates the NOTICE only; it must
#: never gate :func:`is_active`.
_notice_emitted: bool = False
_NOTICE_LOCK: Final[threading.Lock] = threading.Lock()


def request_from_argv(argv: Sequence[str] | None = None) -> bool:
    """Record whether ``--dev`` was passed. Returns what it recorded.

    Idempotent and safe to call from both entrypoints (``run.py`` and the
    app factory), because a container that execs hypercorn directly never
    reaches ``run.py``'s ``main()``.
    """
    global _requested
    _requested = DEV_FLAG in list(argv if argv is not None else sys.argv[1:])
    return _requested


def is_requested() -> bool:
    """True when the flag was passed. NOT the same as active."""
    return _requested


def reset() -> None:
    """Clear all dev-mode state. Tests only — no runtime caller."""
    global _requested, _notice_emitted
    _requested = False
    with _NOTICE_LOCK:
        _notice_emitted = False


#: PenguinTech product domains, from penguintech.md's product table.
#:
#: general.md's dev-mode domain condition names "``*.penguincloud.io``,
#: ``*.penguintech.cloud``, ``*.localhost.local``, product ``.app`` domains".
#: The first three are exactly ``penguin_licensing``'s licence-bypass list,
#: which is reused rather than copied. The product ``.app`` domains are NOT
#: in that list — penguin-licensing does not carry them — so they are
#: declared here, and only for dev mode.
#:
#: That divergence is deliberate and load-bearing in both directions:
#:
#: * it does not widen the LICENCE bypass, which stays exactly as upstream
#:   defines it — a fix wave is no place to loosen a security boundary;
#: * it makes dev mode's domain condition genuinely separable from the
#:   licence bypass, so ``--dev`` unlocking a feature on a ``.app`` domain
#:   is observable proof that dev mode itself did the unlocking, not the
#:   bypass it used to share a predicate with.
#:
#: Unlocking here is narrower than the bypass in every other respect: it
#: additionally requires the flag AND at most one user, and it announces
#: itself.
DEV_MODE_APP_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "currenturl.app",
        "elderrms.app",
        "gough.app",
        "nestdata.app",
        "skauswatch.app",
        "squawkmgr.app",
        "icecharts.app",
        "tobogganing.app",
        "waddleai.app",
        "waddles.app",
        "penguincloud.app",
    }
)


def resolved_host() -> str:
    """The host this deployment is configured to answer on.

    Configuration only — never the request's ``Host`` header. A header is
    supplied by the caller, and the caller here is the party the single-user
    cap exists to constrain; letting them name the domain would let them
    choose whether the condition passes. See
    :func:`app.licensing.configured_host`.
    """
    return configured_host()


def _matches_app_domain(host: str) -> bool:
    """Dot-boundary match against :data:`DEV_MODE_APP_DOMAINS`.

    Same semantics as penguin-licensing's matcher: the bare apex matches and
    a label boundary is required, so ``evilgough.app`` never matches
    ``gough.app``.
    """
    bare = host.split(":")[0].lower()
    return any(bare == domain or bare.endswith(f".{domain}") for domain in DEV_MODE_APP_DOMAINS)


def domain_permits() -> bool:
    """True when the deployment domain is PenguinTech-controlled."""
    host = resolved_host()
    if not host:
        return False
    return host_is_license_exempt(host) or _matches_app_domain(host)


async def user_count() -> int:
    """Count users in the identity table. Server-side, always.

    Never a claim, never a header, never a cached number: the count is the
    load-bearing half of the cap, and anything a client can influence is not
    a count. A database error answers a number that FAILS the condition
    rather than raising — an unreadable identity table must make dev mode
    inert, not make the portal 500.
    """
    try:
        db = get_db()
        return int(await db(db.users.id > 0).count())
    except Exception:
        log.warning("dev_mode_user_count_failed", exc_info=True)
        return MAX_DEV_MODE_USERS + 1


async def is_active() -> bool:
    """True when all three conditions hold, right now.

    Recomputed on every call. The user count in particular is re-read, so a
    deployment that grows past one user deactivates immediately rather than
    at the next restart.
    """
    if not _requested:
        return False
    if not domain_permits():
        return False
    count = await user_count()
    if count > MAX_DEV_MODE_USERS:
        return False

    _announce_once(count)
    return True


def _announce_once(user_count: int) -> None:
    """Emit the WARN log and the verbatim stderr notice, once per process.

    general.md requires the activation log to carry "the resolved domain and
    user count". The count is the OBSERVED one, passed in from the check
    that just read it — logging ``MAX_DEV_MODE_USERS`` instead would print
    the constant 1 forever and tell an auditor nothing about the deployment
    that actually activated.

    The notice is repeated into the log line deliberately: an operator who
    did not start the process never sees the console, and a licensing
    warning nobody can find afterwards is not a warning.
    """
    global _notice_emitted
    with _NOTICE_LOCK:
        if _notice_emitted:
            return
        _notice_emitted = True

    host = resolved_host()
    print(DEV_MODE_NOTICE, file=sys.stderr, flush=True)
    log.warning(
        "dev_mode_active",
        domain=host,
        user_count=user_count,
        max_users=MAX_DEV_MODE_USERS,
        notice=DEV_MODE_NOTICE,
    )


def announce_at_startup() -> None:
    """Print the notice at boot when the flag was passed.

    Startup cannot yet know the user count (no database, no request), so
    this deliberately announces on the REQUEST alone. Telling an operator
    what mode they asked for is not the same as claiming it is active, and
    the message says so — the alternative is a process that silently
    ignores the flag when a condition fails and gives the operator nothing
    to debug with.
    """
    if not _requested:
        return
    print(DEV_MODE_NOTICE, file=sys.stderr, flush=True)
    log.warning(
        "dev_mode_requested",
        domain=resolved_host() or "(unresolved at startup)",
        detail=(
            "--dev passed; activation additionally requires a "
            "PenguinTech-controlled domain and at most "
            f"{MAX_DEV_MODE_USERS} user, re-evaluated per request"
        ),
        notice=DEV_MODE_NOTICE,
    )


async def user_creation_refusal() -> tuple[dict[str, Any], int] | None:
    """The refusal when the dev-mode user cap blocks a new user, else None.

    Called by every route that creates a user, BEFORE it creates one, so
    the operator gets a clear reason instead of a generic failure.
    :func:`assert_user_creation_allowed` is the backstop underneath, for
    call sites that forget.

    Answers with the SAME shape and status as every other scale wall
    (:func:`app.quotas.scale_refusal_body`, 402). It used to be a 403 whose
    body shared no key with the quota refusals, so one class of problem —
    "this deployment may not grow any further" — arrived at the client in
    two unrelated forms and the upgrade UI had to special-case this one.
    ``error`` still names the specific cause; ``required_tier`` is null
    because no tier lifts this cap: the remedy is dropping ``--dev`` and
    licensing the deployment, which the message says.
    """
    if not await is_active():
        return None
    count = await user_count()
    if count < MAX_DEV_MODE_USERS:
        return None

    from . import licensing, quotas

    log.warning("dev_mode_user_cap_refused", user_count=count)
    return (
        quotas.scale_refusal_body(
            error="dev_mode_user_cap",
            message=(
                "Development mode (--dev) is limited to "
                f"{MAX_DEV_MODE_USERS} user. Remove the --dev flag and "
                "apply a commercial license to add more users."
            ),
            dimension="users",
            limit=MAX_DEV_MODE_USERS,
            current=count,
            current_tier=await licensing.resolve_tier(),
            required_tier=None,
        ),
        quotas.SCALE_REFUSAL_STATUS,
    )


class DevModeUserCapExceededError(RuntimeError):
    """Raised by the model-layer backstop when the cap would be breached."""


async def assert_user_creation_allowed() -> None:
    """Backstop enforced beneath every user-creation path.

    The routes above answer a clean 403; this exists because a cap enforced
    at only *some* call sites is not a cap. A future route, a seeding
    script or a background job that inserts a user without asking gets an
    exception rather than a silent breach of the single-user limit.
    """
    if not await is_active():
        return
    if await user_count() >= MAX_DEV_MODE_USERS:
        raise DevModeUserCapExceededError(f"development mode permits {MAX_DEV_MODE_USERS} user")

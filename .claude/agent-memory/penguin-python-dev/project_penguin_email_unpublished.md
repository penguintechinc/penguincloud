---
name: project-penguin-email-unpublished
description: penguin-email (packages/python-email in penguin-libs) is not published to PyPI yet — stdlib smtplib is the fallback for SMTP work in penguincloud until it ships
metadata:
  type: project
---

`penguin_email` exists at `~/code/penguin-libs/packages/python-email`
(pyproject version 0.1.0) but `pip index versions penguin-email` / a PyPI
lookup 404s — it has never been published. `backend.md`'s penguin-libs
package map lists it, but it is aspirational for this product until
someone actually publishes it.

**Consequence for penguincloud (portal-api) work:** you cannot add it to
`requirements.in` — there is nothing on PyPI to hash-pin against, and
`uv pip compile --generate-hashes` would fail to resolve it. A local git/
path dependency isn't viable either (only works on a dev machine with that
checkout, not in CI/Docker).

**How to apply:** when a service needs to send email and `penguin-email`
isn't available, use Python's stdlib `smtplib` + `ssl` (enforce
`TLSVersion.TLSv1_2` minimum per security.md) rather than blocking on the
package or reimplementing a bespoke client library. Read SMTP config via
`os.getenv` at call time (not cached at import), matching this repo's
existing convention (`app/flags.py`'s `POSTHOG_KEY` lookup, `app/config.py`'s
`SECRET_KEY`/`DB_PASS`) — there is no `penguin-sal` SecretClient wired into
this service either, so plain env vars is the locally-consistent choice,
not a shortcut.

Revisit this the moment `penguin-email` actually appears in `pip index
versions penguin-email` — the stdlib transport should be swapped for it at
that point, not kept as permanent local debt.

See [[env-toolchain-constraints]] for the broader "packages the map lists
that aren't actually resolvable yet" pattern (penguin-dal's editable-install
drift is the other instance of this class).

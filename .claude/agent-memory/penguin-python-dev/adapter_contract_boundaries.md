---
name: adapter-contract-boundaries
description: penguincloud adapter contract v2 — where the security boundary is, and the two allowlist traps that silently over-match
metadata:
  type: project
---

`services/portal-api/app/adapters/base.py` states the boundary decision in its
module docstring, and it is settled — do not re-litigate it:

> The allowlist decides **which caller-supplied paths are forwarded**.
> The transport decides **where the stored credential may go**.

The proxy is the untrusted-input path and the only thing `route_allowlist`
governs. Adapter methods are trusted server-side code; `transport.request`
pins every call to the origin of `ctx.base_url` and raises
`CredentialEgressError` before the socket.

**Which mutations go where** (settled in 4G fix wave 1, stated in `base.py`):
a mutation whose result the portal must interpret — anything returning an
`Operation` to poll — goes through a **typed adapter method on a portal
route**; everything else may be proxied. The proxy is a byte pipe: it forwards
the product's `202` verbatim, so `ActionResult.operations` is unreachable
through it and the UI can only invalidate-and-hope. `POST .../actions/{action}`
exposes `perform_action`; `deploy` and `biome upgrade` were REMOVED from
Gough's allowlist accordingly.

**Two allowlist traps that pass review and fail a matrix test** (both were
live defects in Task 4G, neither found by reading the rules):

1. **A permissive `[^/]+` id pattern allowlists literal sub-collections.**
   `^/api/v1/agents/[^/]+\Z` matched `/api/v1/agents/enrollment-keys` — the
   route that lists agent enrollment credentials — as though it were an id.
   Fixed at the contract: use `ID_INT` / `ID_UUID` / `ID_SLUG`, enforced
   registry-wide by `tests/api/test_adapter_registry.py`.

   **Enforce this as an allowlist, never a blocklist.** The first attempt
   banned the substrings `[^/]+ [^/]* .+ .*` — and `\w+`, `[^/]{1,64}`,
   `[A-Za-z0-9_-]+` and `\S+` all sailed through, each re-admitting `enroll` /
   `refresh` / `groups`. `APPROVED_ID_PATTERNS` now requires every non-literal
   segment to BE an approved shape. Two consequences worth keeping: parse
   segments individually (a whole-string substring match cannot say which part
   of a rule is wrong), and make the splitter **character-class aware** —
   `[^/]+` contains a `/` inside a class, so a naive split mangles the exact
   input the checker exists to describe. Keep every adapter segment either a
   plain literal or exactly an approved constant (`health(z)?` was split into
   two rules) so the checker never has to classify regex shapes heuristically.
   The structural check is **blind to routes the adapter does not declare** —
   it compares id patterns only against that adapter's own literals, and
   `enrollment-keys` was never in the allowlist to compare against. The portal
   cannot enumerate a product's route table, so declare it:
   `Adapter.unexposed_routes` lists concrete `(method, path)` requests the
   proxy must refuse, mandatory for any adapter using a variable id segment.
   Both layers are needed — `\w+` is caught only by the shape check (it cannot
   match `enrollment-keys` because of the hyphen, and the declaration is
   method-scoped).

2. **Percent-encoded separators bypassed `normalize_proxy_path`.** Its
   segment scan splits on literal slashes, so `/nodes/..%2fadmin` was one
   segment to the portal and a traversal at any product that decodes it. The
   `%2e` check did not cover it (the segment is `..%2fadmin`, not `..`). Fixed
   there; the same class applies to any new path validation.

**Trailing slashes are load-bearing and asymmetric.** Products are Quart apps,
so Werkzeug's default `strict_slashes` governs: a request MISSING a registered
trailing slash gets a **308**, one carrying a slash the route does not declare
gets a flat **404 with no redirect back**. The portal transport does not follow
redirects and the proxy strips `location`, so BOTH surface to the user as an
empty table rather than an error. Gough registers `route("/")` for
nodes/biomes/agents but `route("/groups")` without one — so a per-kind table of
exact route shapes is required; appending `/` uniformly is a defect in the
other direction.

**How to apply:** write the allowlist matrix as *deny* cases first, naming the
hazard for each, and add structural assertions (every mutating verb requires
manage; no rule admits `/auth/*`; no id pattern matches a route literal). An
allowlist test that only checks happy paths passes just as well against `^/`.

**The escaped tenant placeholder is a LITERAL segment, not an id shape**
(settled 4N, the first adapter to use a tenant-addressed rule). The proxy
matches the allowlist at `proxy.py:444` and substitutes at `:482`, so a rule
must carry `{tenant}` verbatim; `re.escape` makes it look like a pattern to
`_is_literal`, which rejected it. Fixed in the test helper by **exact
equality** with `TENANT_PLACEHOLDER_PATTERN` — never `startswith`, which
admits `\{tenant\}|.*` and allowlists the whole path space beneath a rule
that reads as tenant-scoped. Adding it to `APPROVED_ID_PATTERNS` instead
would declare a fixed literal to be an approved id shape, accepted in every
id slot in every adapter.

Also settled 4N: the sibling-literal check is **prefix-scoped** — it only
compares an id slot against literals under the *same* leading segments. So
`/cost-report/summary` and `/data-resources/{ID_SLUG}` do not collide, and a
rule pair only needs rethinking when the prefixes genuinely match.

Long-running work uses the `Operation` contract (added 4G): report `state`
normalised for control flow AND `status` verbatim for display; never
synthesise `progress`; keep the poll key self-contained (fold a parent id into
the operation id when the product nests the route).

See [[project-portal-scope-vocabulary]], [[feedback-gates-block-push]],
[[feedback-revert-verification]].

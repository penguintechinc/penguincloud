/**
 * The exact proxy paths for Nest's collections.
 *
 * Extracted into a constant of its own for the reason `goughPaths.ts` was:
 * these strings are a contract with the product, and a call site is not where
 * a reader can check them.
 *
 * Two things about their shape are load-bearing.
 *
 * **No trailing slash, anywhere.** Nest's 27 route registrations — 21 distinct
 * paths, six declared twice for a second method — carry none
 * (`~/code/nest/apps/api/app.py`), the opposite of Gough. Under Werkzeug's
 * default `strict_slashes` a request carrying a slash the route does not
 * declare gets a flat 404 with no redirect back — which, since the portal
 * transport does not follow redirects, surfaces as an empty table rather than
 * an error.
 *
 * **`{tenant}` is sent literally.** It is not a value this module interpolates:
 * the portal matches the allowlist rule against the path as written, then
 * substitutes the tenant's external id from `product_tenant_map`. Filling it in
 * here would send a portal tenant id to Nest and miss the allowlist besides —
 * the browser never learns, and must never choose, the product-side id.
 *
 * `tests/api/test_nest_webui_paths.py` builds the expected values with the
 * adapter's own `tenant_path()` and asserts each entry both matches and is
 * admitted by the proxy allowlist, so neither side can drift alone.
 */

/** Collections the Nest screens fetch through the proxy. */
export const NEST_COLLECTION_PATHS = {
  databases: "api/v1/tenants/{tenant}/data-resources",
  snapshots: "api/v1/tenants/{tenant}/snapshots",
  costReport: "api/v1/tenants/{tenant}/cost-report",
  costSummary: "api/v1/tenants/{tenant}/cost-report/summary",
} as const;

/**
 * The key each collection's rows arrive under.
 *
 * There is no shared envelope. Only data-resources answers `items`; snapshots
 * answer `snapshots`, protection policies `policies`, search pools
 * `searchPools` (`~/code/nest/apps/api/handlers/protection.py:26,206`,
 * `handlers/searchpool.py:25`, `handlers/dataresource.py:47`).
 *
 * Reading `items` for all of them — and returning `[]` when it was absent —
 * is what made the Snapshots tab state "No snapshots have been taken from this
 * resource" no matter what Nest answered. An unrecognised shape now throws
 * instead, because the only reading an operator can give an empty list is
 * "there are none".
 *
 * `tests/api/test_nest_webui_paths.py` compares this table to
 * `COLLECTION_ENVELOPE_KEYS` in `app/adapters/nest/mapping.py`, which is in
 * turn bound to Nest's own handlers, so neither side can drift alone.
 */
export const NEST_COLLECTION_ENVELOPE_KEYS = {
  databases: "items",
  snapshots: "snapshots",
} as const;

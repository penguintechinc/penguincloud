/**
 * The exact proxy paths for Nest's collections.
 *
 * Extracted into a constant of its own for the reason `goughPaths.ts` was:
 * these strings are a contract with the product, and a call site is not where
 * a reader can check them.
 *
 * Two things about their shape are load-bearing.
 *
 * **No trailing slash, anywhere.** Nest registers all 27 of its routes without
 * one (`~/code/nest/apps/api/app.py`), the opposite of Gough. Under Werkzeug's
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
 * Path of one data-resource, addressed by NAME.
 *
 * Nest identifies a DataResource by `name` in every route — `/{name}`, never
 * `/{id}` — even though the record also carries a UUID. Feeding the UUID back
 * would build a detail link that 404s, which is why the adapter maps
 * `Resource.id` to the name and keeps the UUID in metadata.
 */
export function nestDatabasePath(name: string): string {
  return `${NEST_COLLECTION_PATHS.databases}/${encodeURIComponent(name)}`;
}

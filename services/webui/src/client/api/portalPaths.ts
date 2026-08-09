/**
 * The portal's own URL shapes, declared once.
 *
 * Why this module exists
 * ======================
 * The browser was calling `/api/v1/proxy/{id}/{path}` while the portal
 * registers `/api/v1/products/{id}/proxy/{path}`. Every proxied product call —
 * all three Gough tables, its create/update/delete verbs, and the Elder and
 * SkausWatch overview cards — therefore reached a route that does not exist.
 *
 * Nothing caught it. `test_gough_webui_paths.py` pins the PRODUCT-relative
 * part of the path (the trailing slash that decides 308-vs-404 at Gough), and
 * pins it well; but it compares the fragment the browser hands to `proxyApi`,
 * not the portal URL `proxyApi` then builds around it. The jest suite asserted
 * the same fragment by stripping the prefix with `^/proxy/\d+/` — a regex
 * written from the broken value, so it could only ever agree with it.
 *
 * The fix is structural rather than a corrected string: the rule below is the
 * single place the portal's proxy URL is spelled on this side, and
 * `tests/api/test_webui_portal_paths.py` compares it against the rule Quart
 * actually registers — read from the live `url_map`, not transcribed. A change
 * to either side that does not reach the other turns that test red.
 */

/** `baseURL` of the axios instance in `lib/api.ts`. */
export const API_BASE_PATH = "/api/v1";

/**
 * The proxy rule as the portal registers it, in OpenAPI placeholder syntax.
 *
 * Kept as a template rather than a prefix string so the Python guard can
 * compare it to `str(rule)` from the Quart `url_map` after a mechanical
 * `<int:connection_id>` → `{connection_id}` rewrite — no hand-transcription
 * of the portal's routing on either side.
 */
export const PORTAL_PROXY_RULE =
  "/api/v1/products/{connection_id}/proxy/{proxy_path}";

/**
 * Build the `url` for an axios call through the product proxy.
 *
 * Returns a path relative to {@link API_BASE_PATH}, because that is what the
 * shared axios instance prepends. `productPath` is passed through verbatim:
 * its exact bytes are the contract with the product (a trailing slash is
 * load-bearing — see `goughPaths.ts`), and encoding it here would corrupt both
 * the separators and the `{tenant}` placeholder the portal substitutes.
 */
export function proxyRequestUrl(
  connectionId: number,
  productPath: string,
): string {
  return `/products/${connectionId}/proxy/${productPath}`;
}

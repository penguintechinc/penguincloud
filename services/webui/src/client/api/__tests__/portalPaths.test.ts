/**
 * The proxy URL the browser builds must be the rule the portal registers.
 *
 * This is the assertion whose absence let `/api/v1/proxy/{id}/...` ship
 * against a portal serving `/api/v1/products/{id}/proxy/...`. The jest suite
 * that "covered" the proxy bindings stripped the prefix with `^/proxy/\d+/`
 * before asserting, so it agreed with the broken value by construction.
 *
 * Here the built URL is compared to {@link PORTAL_PROXY_RULE} — the same
 * constant `tests/api/test_webui_portal_paths.py` compares against Quart's
 * live `url_map`. Neither side asserts against itself.
 */

import {
  API_BASE_PATH,
  PORTAL_PROXY_RULE,
  proxyRequestUrl,
} from "../portalPaths";

/** Fill the rule's placeholders, mirroring what the router matches. */
function fillRule(connectionId: number, productPath: string): string {
  return PORTAL_PROXY_RULE.replace(
    "{connection_id}",
    String(connectionId),
  ).replace("{proxy_path}", productPath);
}

describe("proxyRequestUrl", () => {
  it("resolves to the portal rule once the axios baseURL is applied", () => {
    const productPath = "api/v1/nodes/";

    const absolute = API_BASE_PATH + proxyRequestUrl(7, productPath);

    expect(absolute).toBe(fillRule(7, productPath));
  });

  it("is relative to the baseURL, never absolute", () => {
    // An absolute path here would be prepended to the baseURL by axios and
    // produce /api/v1/api/v1/... — a 404 that looks like a routing bug.
    expect(proxyRequestUrl(7, "api/v1/nodes/")).toBe(
      "/products/7/proxy/api/v1/nodes/",
    );
  });

  it("preserves the product path byte for byte", () => {
    // The trailing slash decides 308-vs-404 at the product, and `{tenant}` is
    // substituted by the portal after allowlist matching — encoding either
    // breaks a request that would otherwise be admitted.
    const tenantScoped = "api/v1/tenants/{tenant}/cost-report";

    expect(proxyRequestUrl(3, tenantScoped)).toBe(
      `/products/3/proxy/${tenantScoped}`,
    );
    expect(proxyRequestUrl(3, "api/v1/biomes/groups")).toBe(
      "/products/3/proxy/api/v1/biomes/groups",
    );
  });
});

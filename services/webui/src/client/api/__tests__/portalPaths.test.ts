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
  portalUrl,
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

describe("portalUrl builders", () => {
  // Every builder is bound to a Quart endpoint by
  // `tests/api/test_webui_portal_paths.py`; these assert the TEXT each one
  // produces, which that guard compares only structurally. Both matter: a
  // builder can have the right shape and the wrong literal segment.

  it("addresses own profile and own password as SEPARATE routes", () => {
    // `PUT /auth/me` was a 405 — auth serves GET only. And the password is not
    // a field on the profile: it needs the current password and is verified
    // separately, which is why the portal splits them.
    expect(portalUrl.ownProfile()).toBe("/users/me");
    expect(portalUrl.ownPassword()).toBe("/users/me/password");
  });

  it("addresses tenants, members and the provider rollup", () => {
    expect(portalUrl.tenants()).toBe("/tenants");
    expect(portalUrl.tenant(4)).toBe("/tenants/4");
    expect(portalUrl.tenantSwitch(4)).toBe("/tenants/4/switch");
    expect(portalUrl.tenantUsage(4)).toBe("/tenants/4/usage");
    expect(portalUrl.tenantMembers(4)).toBe("/tenants/4/members");
    expect(portalUrl.tenantMember(4, 9)).toBe("/tenants/4/members/9");
    // TENANT-scoped, not /dashboard/rollup — see dashboard.ts.
    expect(portalUrl.tenantDashboardRollup(4)).toBe(
      "/tenants/4/dashboard/rollup",
    );
  });

  it("addresses the four dashboard reads", () => {
    expect(portalUrl.dashboardOverview()).toBe("/dashboard/overview");
    expect(portalUrl.dashboardHealth()).toBe("/dashboard/health");
    expect(portalUrl.dashboardActivity()).toBe("/dashboard/activity");
    expect(portalUrl.dashboardAlerts()).toBe("/dashboard/alerts");
  });

  it("encodes a member id rather than letting it compose a path", () => {
    expect(portalUrl.tenantMember(4, 9)).toBe("/tenants/4/members/9");
    expect(portalUrl.resource(1, "database", "a b")).toBe(
      "/products/1/resources/database/a%20b",
    );
  });
});

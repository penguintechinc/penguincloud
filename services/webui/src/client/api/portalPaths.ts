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

/**
 * Every TYPED portal route the browser calls, in OpenAPI placeholder syntax.
 *
 * The proxy rule above was single-sourced after it shipped broken. The typed
 * routes were not: `nestResources.ts` and `goughOperations.ts` hand-spelled ten
 * URLs between them and nothing tied any of them to Quart's `url_map`, so the
 * same defect one layer over was equally unguarded — a renamed parameter or an
 * added `url_prefix` would 404 every write with no test failing.
 *
 * `test_webui_portal_paths.py` compares each entry here to the rule Quart
 * registers for the named endpoint, read from the live `url_map`. The map's
 * VALUES are the Quart endpoint names, so the assertion cannot be satisfied by
 * a route that does not exist.
 *
 * These same strings are the path keys of `schema.d.ts` (generated from
 * `openapi/v1.yaml`), so the OpenAPI spec is a third check on the same text.
 *
 * **The table is one-directional.** It is enforced from the webui call sites:
 * every `/products` or `/tenants` URL built anywhere under `src/client` must
 * come from a `portalUrl` builder, and every rule here must resolve against
 * `url_map`. It does NOT enforce the reverse — the portal can register a typed
 * route with no browser caller and nothing here will notice, which is correct
 * (a CLI-only or service-to-service route is not the webui's business) but is
 * worth knowing before treating this as an inventory of the portal's API.
 */
export const PORTAL_TYPED_RULES = {
  "/api/v1/products": "products.list_products",
  "/api/v1/products/health": "health_api.get_products_health",
  "/api/v1/products/types": "products.list_product_types",
  "/api/v1/products/{product_id}": "products.get_product",
  "/api/v1/products/{product_id}/health": "products.get_product_health",
  "/api/v1/products/{product_id}/metrics": "operations.product_metrics",
  "/api/v1/products/{product_id}/operations": "operations.list_operations",
  "/api/v1/products/{product_id}/operations/{kind}/{operation_id}":
    "operations.get_operation",
  "/api/v1/products/{product_id}/operations/{kind}/{operation_id}/cancel":
    "operations.cancel_operation",
  "/api/v1/products/{product_id}/operations/{kind}/{operation_id}/logs":
    "operations.operation_logs",
  "/api/v1/products/{product_id}/resources/{kind}": "resources.create_resource",
  "/api/v1/products/{product_id}/resources/{kind}/{resource_id}":
    "resources.delete_resource",
  "/api/v1/products/{product_id}/resources/{kind}/{resource_id}/actions/{action}":
    "operations.perform_resource_action",
  "/api/v1/products/{product_id}/schema": "products.get_product_schema",
  "/api/v1/products/{product_id}/test": "products.test_product_connection",
  "/api/v1/tenants": "tenants.list_user_tenants",
  "/api/v1/tenants/{tenant_id}": "tenants.get_tenant_endpoint",
  "/api/v1/tenants/{tenant_id}/dashboard/rollup":
    "tenants.get_dashboard_rollup",
  "/api/v1/tenants/{tenant_id}/members": "tenants.list_tenant_members",
  "/api/v1/tenants/{tenant_id}/members/{member_user_id}":
    "tenants.update_tenant_member_role",
  "/api/v1/tenants/{tenant_id}/switch": "tenants.switch_tenant",
  "/api/v1/tenants/{tenant_id}/usage": "tenants.get_tenant_usage",
  "/api/v1/features": "features.get_features",
  "/api/v1/dashboard/activity": "dashboard.dashboard_activity",
  "/api/v1/dashboard/alerts": "dashboard.dashboard_alerts",
  "/api/v1/dashboard/health": "dashboard.dashboard_health",
  "/api/v1/dashboard/overview": "dashboard.dashboard_overview",
  "/api/v1/users/me": "users.update_profile",
  "/api/v1/users/me/password": "users.change_password",
} as const;

/** Encoded path segment — an id never composes a new path. */
const seg = (value: string | number): string =>
  encodeURIComponent(String(value));

/**
 * Builders for the typed routes above, so no call site spells one itself.
 *
 * Each returns a path relative to {@link API_BASE_PATH} (what the shared axios
 * instance prepends) and is built from the corresponding `PORTAL_TYPED_RULES`
 * key by substitution, so a rule the portal stopped serving cannot survive
 * here as a literal string in a call site nobody re-reads.
 */
export const portalUrl = {
  /** Collection: list (GET) and register (POST) share one rule. */
  products: (): string => "/products",

  productTypes: (): string => "/products/types",

  product: (productId: number): string => `/products/${productId}`,

  productHealth: (productId: number): string => `/products/${productId}/health`,

  productSchema: (productId: number): string => `/products/${productId}/schema`,

  productTest: (productId: number): string => `/products/${productId}/test`,

  metrics: (productId: number): string => `/products/${productId}/metrics`,

  operations: (productId: number): string =>
    `/products/${productId}/operations`,

  operation: (productId: number, kind: string, operationId: string): string =>
    `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}`,

  cancelOperation: (
    productId: number,
    kind: string,
    operationId: string,
  ): string =>
    `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}/cancel`,

  operationLogs: (
    productId: number,
    kind: string,
    operationId: string,
  ): string =>
    `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}/logs`,

  resources: (productId: number, kind: string): string =>
    `/products/${productId}/resources/${seg(kind)}`,

  resource: (productId: number, kind: string, resourceId: string): string =>
    `/products/${productId}/resources/${seg(kind)}/${seg(resourceId)}`,

  resourceAction: (
    productId: number,
    kind: string,
    resourceId: string,
    action: string,
  ): string =>
    `/products/${productId}/resources/${seg(kind)}/${seg(resourceId)}/actions/${seg(action)}`,

  /**
   * Provider rollup. TENANT-scoped, not a `/dashboard/*` route — the caller
   * spelled `/dashboard/rollup` with a `tenant_id` query parameter, which the
   * portal does not register at all.
   */
  tenantDashboardRollup: (tenantId: number): string =>
    `/tenants/${tenantId}/dashboard/rollup`,

  /** Collection: list (GET) and create (POST) share one rule. */
  tenants: (): string => "/tenants",

  tenant: (tenantId: number): string => `/tenants/${tenantId}`,

  tenantSwitch: (tenantId: number): string => `/tenants/${tenantId}/switch`,

  tenantUsage: (tenantId: number): string => `/tenants/${tenantId}/usage`,

  /** Collection: list (GET) and add (POST) share one rule. */
  tenantMembers: (tenantId: number): string => `/tenants/${tenantId}/members`,

  tenantMember: (tenantId: number, userId: number): string =>
    `/tenants/${tenantId}/members/${seg(userId)}`,

  /**
   * Flag state, licensed tier and the dev-mode signal. Authenticated: the
   * response enumerates every integrated product and licensed capability.
   */
  features: (): string => "/features",

  dashboardOverview: (): string => "/dashboard/overview",

  dashboardHealth: (): string => "/dashboard/health",

  dashboardActivity: (): string => "/dashboard/activity",

  dashboardAlerts: (): string => "/dashboard/alerts",

  /**
   * Own profile. `PUT /auth/me` is a 405 — the auth blueprint serves GET only
   * (`auth.get_me`); the writable profile lives on the users blueprint.
   */
  ownProfile: (): string => "/users/me",

  /** Own password. A SEPARATE route from the profile, not a field on it. */
  ownPassword: (): string => "/users/me/password",
} as const;

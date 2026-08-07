/**
 * Application routes. Used by tests to validate that menu items have
 * corresponding routes (regression prevention for dead links).
 *
 * Must be kept in sync with the routes defined in App.tsx.
 */

export const APP_ROUTES = [
  "/",
  "/dashboard",
  "/login",
  "/health",
  "/profile",
  "/tenants",
  "/tenants/new",
  "/tenants/:id",
  "/users",
  "/users/:id",
  "/connections",
  "/connections/new",
  "/connections/:id",
  "/teams",
  "/audit",
  "/settings",
  "/products/:id",
] as const;

/**
 * Menu item href routes (subset of APP_ROUTES, specific to sidebar navigation).
 * These should all be present in APP_ROUTES or parameterized routes should match.
 */
export const MENU_ITEM_ROUTES = [
  "/",
  "/health",
  "/profile",
  "/tenants",
  "/users",
  "/connections",
  "/teams",
  "/audit",
  "/settings",
  "/products/gough/nodes",
  "/products/gough/biomes",
  "/products/gough/clusters",
  "/products/gough/agents",
  "/products/nest/databases",
  "/products/nest/servers",
  "/products/nest/workflows",
  "/products/nest/billing",
  "/products/nest/cloud",
  "/products/tobogganing/sase",
  "/products/tobogganing/sdwan",
  "/products/tobogganing/firewall",
  "/products/tobogganing/wireguard",
  "/products/tobogganing/headend",
] as const;

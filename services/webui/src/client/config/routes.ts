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
  "/products/gough/nodes",
  "/products/gough/biomes",
  "/products/gough/agents",
  "/products/nest/databases",
] as const;

/**
 * Menu item href routes (subset of APP_ROUTES, specific to sidebar navigation).
 *
 * Every entry MUST also appear in `APP_ROUTES` — `menuCategories.test.ts`
 * asserts the subset relation, so a nav entry added here without a route in
 * `App.tsx` fails rather than shipping as a dead link.
 *
 * That assertion is why the Nest category lost its Servers, Workflows and
 * Cloud entries: they were listed here with no route behind them. The
 * dead-link test could not see it, because it only built the categories for a
 * tenant with NO product connections — so no product entry was ever checked.
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
  "/products/gough/agents",
  "/products/nest/databases",
] as const;

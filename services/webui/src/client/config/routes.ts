/**
 * Application routes. Used by tests to validate that menu items have
 * corresponding routes (regression prevention for dead links).
 *
 * Kept in sync with `App.tsx` BY TEST, not by discipline:
 * `config/__tests__/routes.test.ts` parses the `<Route path="...">` table out
 * of `App.tsx` and asserts set equality with `APP_ROUTES`. Until it did, this
 * header said "must be kept in sync" and nothing checked it — so an href
 * present here and absent from the router was still a dead link that passed
 * green, and the whole menu → MENU_ITEM_ROUTES → APP_ROUTES chain terminated
 * in a hand-maintained list.
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
  "/products/nest/billing",
  "/products/tobogganing/clients",
  "/products/tobogganing/clusters",
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
  "/products/nest/billing",
  "/products/tobogganing/clients",
  "/products/tobogganing/clusters",
] as const;

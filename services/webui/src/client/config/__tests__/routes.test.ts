/**
 * `APP_ROUTES` must be what `App.tsx` actually serves.
 *
 * Why this file exists
 * ====================
 * The dead-link chain was rebuilt so that `MENU_ITEM_ROUTES` ⊆ `APP_ROUTES` —
 * a nav entry can no longer be added without a route. But `APP_ROUTES` itself
 * was tied to nothing: its header said "must be kept in sync with the routes
 * defined in App.tsx" and nothing checked it. An href present in `APP_ROUTES`
 * and absent from `App.tsx` was still a dead link that passed green, so the
 * chain terminated in a hand-maintained list rather than in the router.
 *
 * `App.tsx` is read as text rather than rendered: the route table is a static
 * JSX literal, and parsing it is what makes this assert against the file the
 * router is compiled from instead of against a mounted component whose routes
 * would have to be enumerated by navigating to each one.
 *
 * Excluded from the comparison, deliberately:
 * - `path="*"` — the catch-all, which is not a destination anything links to;
 * - layout `<Route>` elements with no `path` at all.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { APP_ROUTES, MENU_ITEM_ROUTES } from "../routes";

// Resolved from jest's rootDir (services/webui) rather than from
// `import.meta.url`, which jest's CJS transform cannot parse.
const APP_TSX = resolve(process.cwd(), "src/client/App.tsx");

/** Every `path="..."` on a `<Route>` in App.tsx, catch-all excluded. */
function routesDeclaredInApp(): string[] {
  const source = readFileSync(APP_TSX, "utf8");
  const found = [...source.matchAll(/<Route\b[^>]*?\bpath="([^"]+)"/g)].map(
    (match) => match[1],
  );

  // A parser that silently found nothing would make every assertion below
  // pass vacuously — the exact failure mode this test exists to end.
  expect(found.length).toBeGreaterThan(10);

  return found.filter((path) => path !== "*");
}

describe("APP_ROUTES", () => {
  it("lists exactly the paths App.tsx registers", () => {
    // Set equality both ways: a route in App.tsx but not here would let a nav
    // entry for it fail review for the wrong reason, and one here but not in
    // App.tsx is a dead link that the menu check would happily accept.
    expect([...APP_ROUTES].sort()).toEqual(routesDeclaredInApp().sort());
  });

  it("declares no route twice", () => {
    expect(new Set(APP_ROUTES).size).toBe(APP_ROUTES.length);
  });

  it("keeps MENU_ITEM_ROUTES a subset of what App.tsx serves", () => {
    // The end of the chain, asserted in one place: menu href → MENU_ITEM_ROUTES
    // → APP_ROUTES → App.tsx. `menuCategories.test.ts` covers the first two
    // links; this covers the last, so no hand-maintained list sits between a
    // sidebar entry and a router path.
    const served = new Set(routesDeclaredInApp());

    expect(MENU_ITEM_ROUTES.filter((href) => !served.has(href))).toEqual([]);
  });

  it("serves a route for both Nest screens", () => {
    // Named rather than left to the set comparison: Servers, Cloud and
    // Workflows were removed from the sidebar because nothing serves them, and
    // the two that remain must be genuinely routed rather than merely listed.
    const served = new Set(routesDeclaredInApp());

    expect(served.has("/products/nest/databases")).toBe(true);
    expect(served.has("/products/nest/billing")).toBe(true);
    expect(served.has("/products/nest/servers")).toBe(false);
  });
});

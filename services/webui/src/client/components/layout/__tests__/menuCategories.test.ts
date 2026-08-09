/**
 * Sidebar category construction tests.
 *
 * The product-category gate is the interesting rule: a category appears only
 * when a connection for that product exists AND its feature gate is on.
 */

import { buildMenuCategories, PRODUCT_ITEMS } from "../menuCategories";
import { isProductEnabled } from "../../../lib/featureGates";
import { APP_ROUTES, MENU_ITEM_ROUTES } from "../../../config/routes";
import type { ProductConnection } from "../../../types";

jest.mock("../../../lib/featureGates");

const allowAll = () => true;

function connection(productType: string): ProductConnection {
  return { product_type: productType } as ProductConnection;
}

describe("buildMenuCategories", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (isProductEnabled as jest.Mock).mockReturnValue(true);
  });

  it("always includes Home and Organization", () => {
    const headers = buildMenuCategories([], allowAll).map((c) => c.header);

    expect(headers).toEqual(["Home", "Organization"]);
  });

  it("adds a product category when connected and gated on", () => {
    const headers = buildMenuCategories([connection("gough")], allowAll).map(
      (c) => c.header,
    );

    expect(headers).toContain("Gough");
  });

  it("offers no Clusters entry for Gough", () => {
    // Gough registers no cluster collection endpoint, and neither its Node
    // nor its Biome model carries a cluster column — so no cluster id is
    // obtainable from any screen the portal has. A Clusters link could only
    // lead to a form asking the operator to type a UUID by hand. Asserted
    // rather than left implicit because the entry existed in Phase 2F and
    // removing it is a decision, not an omission. See task-4G-report.md.
    const gough = buildMenuCategories([connection("gough")], allowAll).find(
      (category) => category.header === "Gough",
    );

    expect(gough?.items.map((item) => item.name)).toEqual([
      "Nodes",
      "Biomes",
      "Agents",
    ]);
  });

  it("omits a connected product whose gate is off", () => {
    (isProductEnabled as jest.Mock).mockImplementation(
      (key) => key !== "gough",
    );

    const headers = buildMenuCategories(
      [connection("gough"), connection("nest")],
      allowAll,
    ).map((c) => c.header);

    expect(headers).not.toContain("Gough");
    expect(headers).toContain("Nest");
  });

  it("omits a gated-on product with no connection", () => {
    const headers = buildMenuCategories([], allowAll).map((c) => c.header);

    expect(headers).not.toContain("Tobogganing");
  });

  it("keeps product categories in a stable order", () => {
    // Order follows PRODUCT_ITEMS declaration order, not connection order —
    // the connections are deliberately passed in a different sequence.
    const headers = buildMenuCategories(
      [connection("tobogganing"), connection("nest"), connection("gough")],
      allowAll,
    ).map((c) => c.header);

    expect(headers).toEqual([
      "Home",
      "Gough",
      "Nest",
      "Tobogganing",
      "Organization",
    ]);
  });

  it("filters items by role", () => {
    const viewerOnly = (roles?: string[]) => !roles || roles.includes("viewer");

    const categories = buildMenuCategories([], viewerOnly);
    const org = categories.find((c) => c.header === "Organization");

    expect(org).toBeUndefined();
    expect(categories.map((c) => c.header)).toEqual(["Home"]);
  });

  it("keeps Organization when at least one item is permitted", () => {
    const maintainer = (roles?: string[]) =>
      !roles || roles.includes("maintainer");

    const org = buildMenuCategories([], maintainer).find(
      (c) => c.header === "Organization",
    );

    expect(org?.items.map((i) => i.name)).toEqual([
      "Tenants",
      "Teams",
      "Connections",
      "Settings",
    ]);
  });

  it("treats an unmapped product_type as its own gate key", () => {
    (isProductEnabled as jest.Mock).mockReturnValue(true);

    const headers = buildMenuCategories(
      [connection("something-new")],
      allowAll,
    ).map((c) => c.header);

    // No category is declared for it, so nothing is added — but it must not
    // throw or suppress the standing categories either.
    expect(headers).toEqual(["Home", "Organization"]);
  });

  it("all menu items have valid hrefs (regression test for dead links)", () => {
    // Connections are DERIVED from PRODUCT_ITEMS, not listed. The previous
    // version passed `[]` — no product category was ever constructed, so five
    // Nest and five Tobogganing entries sat here as dead links while a test
    // named "regression test for dead links" stayed green. Naming three
    // products by hand fixed that case and left the same hole open one product
    // wide: a fourth category added tomorrow would be equally unchecked.
    const categories = buildMenuCategories(
      Object.keys(PRODUCT_ITEMS).map(connection),
      allowAll,
    );

    // Valid routes are derived from MENU_ITEM_ROUTES config to prevent silent drift
    const validRoutes = new Set<string>(MENU_ITEM_ROUTES);

    const allItems = categories.flatMap((c) => c.items);
    expect(allItems.length).toBeGreaterThan(0);
    const deadLinks = allItems.filter((item) => !validRoutes.has(item.href));

    if (deadLinks.length > 0) {
      const deadLinksList = deadLinks.map((d) => d.href).join(", ");
      throw new Error(`Dead links found: ${deadLinksList}`);
    }
    expect(deadLinks).toHaveLength(0);
  });

  it("every declared menu route is a route the app actually serves", () => {
    // The check above compares the menu against MENU_ITEM_ROUTES, which is a
    // list of hrefs — so on its own it only proves the two lists agree, not
    // that anything answers them. This ties MENU_ITEM_ROUTES to APP_ROUTES;
    // `config/__tests__/routes.test.ts` then ties APP_ROUTES to the `<Route>`
    // table in App.tsx, so the chain ends at the router rather than at a
    // hand-maintained list.
    const served = new Set<string>(APP_ROUTES);

    const unserved = MENU_ITEM_ROUTES.filter((href) => !served.has(href));

    expect(unserved).toEqual([]);
  });

  it("checks every product category that declares items", () => {
    // Guards the derivation above: if PRODUCT_ITEMS were emptied, or the
    // gate/connection wiring stopped producing categories, the dead-link check
    // would pass by looking at nothing.
    const withItems = Object.entries(PRODUCT_ITEMS)
      .filter(([, { items }]) => items.length > 0)
      .map(([, { header }]) => header);
    const headers = buildMenuCategories(
      Object.keys(PRODUCT_ITEMS).map(connection),
      allowAll,
    ).map((category) => category.header);

    expect(withItems.length).toBeGreaterThan(0);
    withItems.forEach((header) => expect(headers).toContain(header));
  });

  it("offers only the Nest screens that a Nest connection can reach", () => {
    // Nest is four services behind a gateway that routes all of /api to
    // nest-api, and the portal transport pins a connection to one origin. So
    // Servers and Cloud (apps/manager) and Workflows (saga-engine) are not
    // reachable at a Nest connection at all — asserted rather than left
    // implicit because their removal is a decision, not an omission.
    // See task-4N-report.md and penguintechinc/nest#25.
    const nest = buildMenuCategories([connection("nest")], allowAll).find(
      (category) => category.header === "Nest",
    );

    expect(nest?.items.map((item) => item.name)).toEqual([
      "Databases",
      "Billing",
    ]);
  });

  it("omits a product category that has no screens yet", () => {
    // A header with nothing under it reads as a screen that failed to load.
    //
    // Until 4T this was asserted against Tobogganing, which genuinely had no
    // items. Every product now has some, so the rule would otherwise be
    // exercised by nothing — a test that passes because its subject went away
    // is exactly the shape this phase keeps finding. The items are emptied
    // and restored so the code path is still run rather than assumed.
    const target = "gough";
    const saved = PRODUCT_ITEMS[target].items;
    PRODUCT_ITEMS[target].items = [];
    try {
      const headers = buildMenuCategories(
        Object.keys(PRODUCT_ITEMS).map(connection),
        allowAll,
      ).map((c) => c.header);

      expect(headers).not.toContain(PRODUCT_ITEMS[target].header);
      expect(headers).toContain("Tobogganing");
    } finally {
      PRODUCT_ITEMS[target].items = saved;
    }
  });

  it("offers only the Tobogganing screens a portal credential can reach", () => {
    // Firewall and Headend are absent and must stay absent. They are
    // Tobogganing's machine control plane: @require_machine_jwt rejects any
    // token whose `aud` is not "headend", and a portal connection credential
    // carries aud=="tobogganing". No scope grant fixes that — the audience
    // check fails first. Asserted rather than left implicit because their
    // absence is a decision backed by evidence, not an omission.
    const tobogganing = buildMenuCategories(
      [connection("tobogganing")],
      allowAll,
    ).find((category) => category.header === "Tobogganing");
    const names = tobogganing?.items.map((item) => item.name);

    expect(names).toEqual(["Clients"]);
    expect(names).not.toContain("Firewall");
    expect(names).not.toContain("Headend");
  });
});

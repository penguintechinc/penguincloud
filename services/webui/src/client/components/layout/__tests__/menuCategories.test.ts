/**
 * Sidebar category construction tests.
 *
 * The product-category gate is the interesting rule: a category appears only
 * when a connection for that product exists AND its feature gate is on.
 */

import { buildMenuCategories } from "../menuCategories";
import { isProductEnabled } from "../../../lib/featureGates";
import { MENU_ITEM_ROUTES } from "../../../config/routes";
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
    const categories = buildMenuCategories([], allowAll);

    // Valid routes are derived from MENU_ITEM_ROUTES config to prevent silent drift
    const validRoutes = new Set<string>(MENU_ITEM_ROUTES);

    const allItems = categories.flatMap((c) => c.items);
    const deadLinks = allItems.filter((item) => !validRoutes.has(item.href));

    if (deadLinks.length > 0) {
      const deadLinksList = deadLinks.map((d) => d.href).join(", ");
      throw new Error(`Dead links found: ${deadLinksList}`);
    }
    expect(deadLinks).toHaveLength(0);
  });
});

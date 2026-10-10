/**
 * `buildExtensionMenuItems` / `mergeExtensionMenuItems` — pure derivation
 * from `manifest.extensions`, then placement into an EXISTING category by
 * key. Fixtures use invented product types so a passing suite cannot be
 * explained by a hidden per-product branch here.
 */
import {
  buildExtensionMenuItems,
  mergeExtensionMenuItems,
} from "../extensionNav";
import type {
  ConsoleManifest,
  ExtensionSlot,
  ProductManifestEntry,
} from "../../kit/manifestTypes";
import type { MenuCategory } from "@penguintechinc/react-libs";

function entry(
  productType: string,
  extensions: ExtensionSlot[],
): ProductManifestEntry {
  const manifest: ConsoleManifest = {
    manifest_version: 2,
    product_type: productType,
    display_name: `${productType} Display`,
    nav: { items: [] },
    resources: [],
    operations: null,
    metrics: null,
    extensions,
  };
  return { product_id: 1, product_type: productType, manifest };
}

function slot(overrides: Partial<ExtensionSlot> = {}): ExtensionSlot {
  return {
    slot: "page",
    id: "panel",
    label: "Panel",
    resource: null,
    position: 0,
    ...overrides,
  };
}

function category(
  key: string,
  items: MenuCategory["items"] = [],
): MenuCategory {
  return { header: key, collapsible: true, items, key, defaultOpen: false };
}

describe("buildExtensionMenuItems", () => {
  it("returns no groups for an empty manifest list", () => {
    expect(buildExtensionMenuItems([])).toEqual([]);
  });

  it("skips a product with no page slots", () => {
    const groups = buildExtensionMenuItems([
      entry("nav-product", [slot({ slot: "detail_tab" })]),
    ]);

    expect(groups).toEqual([]);
  });

  it("builds one group per product with at least one page slot, keyed by its category", () => {
    const groups = buildExtensionMenuItems([
      entry("nav-product", [slot({ id: "a", label: "A" })]),
    ]);

    expect(groups).toHaveLength(1);
    // "nav-product" is unmapped by menuCategories.ts's product-key table, so
    // `productCategoryKey` falls back to the raw product_type — proving the
    // group is keyed via that lookup, not a copy of it.
    expect(groups[0]?.categoryKey).toBe("nav-product");
    expect(groups[0]?.items).toEqual([
      {
        name: "A",
        href: "/products/nav-product/ext/a",
        icon: expect.anything(),
      },
    ]);
  });

  it("orders items by declared position, not declaration order", () => {
    const groups = buildExtensionMenuItems([
      entry("nav-product", [
        slot({ id: "second", label: "Second", position: 2 }),
        slot({ id: "first", label: "First", position: 1 }),
      ]),
    ]);

    expect(groups[0]?.items.map((item) => item.name)).toEqual([
      "First",
      "Second",
    ]);
  });

  it("excludes non-page slots from the same manifest", () => {
    const groups = buildExtensionMenuItems([
      entry("nav-product", [
        slot({ id: "page-one", label: "Page One" }),
        slot({ id: "tab-one", label: "Tab One", slot: "detail_tab" }),
        slot({ id: "cell-one", label: "Cell One", slot: "cell" }),
      ]),
    ]);

    expect(groups[0]?.items.map((item) => item.name)).toEqual(["Page One"]);
  });

  it("builds an independent group per product, in manifest order", () => {
    const groups = buildExtensionMenuItems([
      entry("product-a", [slot({ id: "a", label: "A" })]),
      entry("product-b", [slot({ id: "b", label: "B" })]),
    ]);

    expect(groups.map((g) => g.categoryKey)).toEqual([
      "product-a",
      "product-b",
    ]);
  });
});

describe("mergeExtensionMenuItems", () => {
  it("returns categories unchanged when there are no groups", () => {
    const categories = [
      category("nav-product", [{ name: "Existing", href: "/x" }]),
    ];

    expect(mergeExtensionMenuItems(categories, [])).toBe(categories);
  });

  it("appends a page-slot item inside its product's existing category, not a separate one", () => {
    const categories = [
      category("nav-product", [{ name: "Existing", href: "/x" }]),
    ];
    const groups = buildExtensionMenuItems([
      entry("nav-product", [slot({ id: "panel", label: "Panel" })]),
    ]);

    const merged = mergeExtensionMenuItems(categories, groups);

    // Same category count — no "nav-product Display Extensions" sibling.
    expect(merged).toHaveLength(1);
    expect(merged[0]?.key).toBe("nav-product");
    expect(merged[0]?.items.map((i) => i.name)).toEqual(["Existing", "Panel"]);
    expect(merged[0]?.items[1]).toMatchObject({
      href: "/products/nav-product/ext/panel",
    });
  });

  it("orders merged items by the slot's declared position", () => {
    const categories = [category("nav-product")];
    const groups = buildExtensionMenuItems([
      entry("nav-product", [
        slot({ id: "second", label: "Second", position: 2 }),
        slot({ id: "first", label: "First", position: 1 }),
      ]),
    ]);

    const merged = mergeExtensionMenuItems(categories, groups);

    expect(merged[0]?.items.map((i) => i.name)).toEqual(["First", "Second"]);
  });

  it("drops a group whose product has no built category — never a dangling nav item", () => {
    const categories = [category("other-product")];
    const groups = buildExtensionMenuItems([
      entry("not-shown-product", [slot({ id: "panel", label: "Panel" })]),
    ]);

    const merged = mergeExtensionMenuItems(categories, groups);

    expect(merged).toEqual(categories);
    expect(merged.flatMap((c) => c.items).some((i) => i.name === "Panel")).toBe(
      false,
    );
  });

  it("leaves a category with no `key` untouched, even if a group's key happens to match its header", () => {
    const categories: MenuCategory[] = [
      { header: "nav-product", collapsible: true, items: [] },
    ];
    const groups = buildExtensionMenuItems([
      entry("nav-product", [slot({ id: "panel", label: "Panel" })]),
    ]);

    const merged = mergeExtensionMenuItems(categories, groups);

    expect(merged[0]?.items).toEqual([]);
  });
});

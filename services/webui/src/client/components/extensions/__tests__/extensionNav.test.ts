/**
 * `buildExtensionMenuCategories` — pure derivation from
 * `manifest.extensions`. Fixtures use invented product types so a passing
 * suite cannot be explained by a hidden per-product branch here.
 */
import { buildExtensionMenuCategories } from "../extensionNav";
import type {
  ConsoleManifest,
  ExtensionSlot,
  ProductManifestEntry,
} from "../../kit/manifestTypes";

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

it("returns no categories for an empty manifest list", () => {
  expect(buildExtensionMenuCategories([])).toEqual([]);
});

it("skips a product with no page slots — a header with nothing under it reads as a failed load", () => {
  const categories = buildExtensionMenuCategories([
    entry("nav-product", [slot({ slot: "detail_tab" })]),
  ]);

  expect(categories).toEqual([]);
});

it("builds one category per product with at least one page slot", () => {
  const categories = buildExtensionMenuCategories([
    entry("nav-product", [slot({ id: "a", label: "A" })]),
  ]);

  expect(categories).toHaveLength(1);
  expect(categories[0]?.header).toBe("nav-product Display Extensions");
  expect(categories[0]?.key).toBe("ext-nav-product");
  expect(categories[0]?.items).toEqual([
    { name: "A", href: "/products/nav-product/ext/a", icon: expect.anything() },
  ]);
});

it("orders items by declared position, not declaration order", () => {
  const categories = buildExtensionMenuCategories([
    entry("nav-product", [
      slot({ id: "second", label: "Second", position: 2 }),
      slot({ id: "first", label: "First", position: 1 }),
    ]),
  ]);

  expect(categories[0]?.items.map((item) => item.name)).toEqual([
    "First",
    "Second",
  ]);
});

it("excludes non-page slots from the same manifest", () => {
  const categories = buildExtensionMenuCategories([
    entry("nav-product", [
      slot({ id: "page-one", label: "Page One" }),
      slot({ id: "tab-one", label: "Tab One", slot: "detail_tab" }),
      slot({ id: "cell-one", label: "Cell One", slot: "cell" }),
    ]),
  ]);

  expect(categories[0]?.items.map((item) => item.name)).toEqual(["Page One"]);
});

it("builds an independent category per product, in manifest order", () => {
  const categories = buildExtensionMenuCategories([
    entry("product-a", [slot({ id: "a", label: "A" })]),
    entry("product-b", [slot({ id: "b", label: "B" })]),
  ]);

  expect(categories.map((c) => c.key)).toEqual([
    "ext-product-a",
    "ext-product-b",
  ]);
});

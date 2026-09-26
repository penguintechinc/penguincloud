import { Puzzle } from "lucide-react";
import type { MenuCategory, MenuItem } from "@penguintechinc/react-libs";
import type { ProductManifestEntry } from "../kit/manifestTypes";
import { productCategoryKey } from "../layout/menuCategories";

/**
 * One product's `page`-slot nav items, tagged with the sidebar category
 * `key` they belong under (see `menuCategories.ts`'s `productCategoryKey`).
 * Deliberately NOT a `MenuCategory` of its own — Design §4.1's escape hatch
 * used to get a standalone `"{display_name} Extensions"` category, which is
 * exactly the UX wart blocking Billing's convergence onto Nest's own
 * category. `mergeExtensionMenuItems` folds these into the product's
 * EXISTING category instead.
 *
 * Purely derived from `manifest.extensions` — no product name, list, or
 * branch anywhere in this module. A brand new product with a `page` slot
 * gets its item placed correctly with zero new webui lines, the same
 * guarantee `manifestCapabilities.ts`'s module doc makes for resources.
 */
export interface ExtensionMenuItemGroup {
  categoryKey: string;
  items: MenuItem[];
}

/**
 * Builds one `ExtensionMenuItemGroup` per product with at least one `page`
 * slot, sorted by declared `position`. A product with zero page slots
 * contributes nothing — an empty group would only ever be dropped by
 * `mergeExtensionMenuItems` anyway, so it is never constructed.
 *
 * Gating is inherited, not re-implemented: `manifests` only contains an
 * entry when `penguincloud.declarative_console` is on AND the tenant is
 * connected to that product — see `useConsoleManifests`'s own doc.
 */
export function buildExtensionMenuItems(
  manifests: ProductManifestEntry[],
): ExtensionMenuItemGroup[] {
  const groups: ExtensionMenuItemGroup[] = [];

  for (const entry of manifests) {
    const pageSlots = entry.manifest.extensions
      .filter((slot) => slot.slot === "page")
      .slice()
      .sort((a, b) => a.position - b.position);

    if (pageSlots.length === 0) continue;

    groups.push({
      categoryKey: productCategoryKey(entry.product_type),
      items: pageSlots.map((slot) => ({
        name: slot.label,
        href: `/products/${entry.product_type}/ext/${slot.id}`,
        icon: Puzzle,
      })),
    });
  }

  return groups;
}

/**
 * Folds each group's items into the matching built category (matched by
 * `category.key === group.categoryKey`), appended after that category's own
 * static items so a product's items always sort before its extensions.
 *
 * A group whose `categoryKey` matches no built category — the product isn't
 * connected, its gate is off, or it declares no other screens — is dropped
 * rather than left dangling: nav placement never outlives the category it
 * depends on, the same rule the old standalone-category version enforced
 * via "no empty header ever renders".
 */
export function mergeExtensionMenuItems(
  categories: MenuCategory[],
  groups: ExtensionMenuItemGroup[],
): MenuCategory[] {
  if (groups.length === 0) return categories;

  const itemsByKey = new Map<string, MenuItem[]>();
  for (const group of groups) {
    const existing = itemsByKey.get(group.categoryKey);
    itemsByKey.set(
      group.categoryKey,
      existing ? [...existing, ...group.items] : group.items,
    );
  }

  return categories.map((category) => {
    const extra =
      category.key !== undefined ? itemsByKey.get(category.key) : undefined;
    if (!extra || extra.length === 0) return category;
    return { ...category, items: [...category.items, ...extra] };
  });
}

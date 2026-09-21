import { Puzzle } from "lucide-react";
import type { MenuCategory } from "@penguintechinc/react-libs";
import type { ProductManifestEntry } from "../kit/manifestTypes";

/**
 * Sidebar categories for every product's `page`-slot extensions — Design
 * §4.1's escape hatch gets its OWN nav entry, independent of
 * `manifestCapabilities.ts` (the capability-subset gate
 * `buildMenuCategories`'s hand-written product categories run behind): a
 * `page` slot is not a resource, so it never needs `isManifestRoutable` to
 * agree a screen can render it losslessly.
 *
 * Purely derived from `manifest.extensions` — no product name, list, or
 * branch anywhere in this function. A brand new product with a `page` slot
 * gets a nav entry here with zero new webui lines, the same guarantee
 * `manifestCapabilities.ts`'s module doc makes for resources.
 *
 * Gating is inherited, not re-implemented: `manifests` only contains an
 * entry when `penguincloud.declarative_console` is on AND the tenant is
 * connected to that product — see `useConsoleManifests`'s own doc.
 */
export function buildExtensionMenuCategories(
  manifests: ProductManifestEntry[],
): MenuCategory[] {
  const categories: MenuCategory[] = [];

  for (const entry of manifests) {
    const pageSlots = entry.manifest.extensions
      .filter((slot) => slot.slot === "page")
      .slice()
      .sort((a, b) => a.position - b.position);

    // A category with nothing under it reads as a screen that failed to
    // load — the same rule `buildMenuCategories` applies to its own
    // categories (`menuCategories.ts`).
    if (pageSlots.length === 0) continue;

    categories.push({
      header: `${entry.manifest.display_name} Extensions`,
      collapsible: true,
      key: `ext-${entry.product_type}`,
      defaultOpen: false,
      items: pageSlots.map((slot) => ({
        name: slot.label,
        href: `/products/${entry.product_type}/ext/${slot.id}`,
        icon: Puzzle,
      })),
    });
  }

  return categories;
}

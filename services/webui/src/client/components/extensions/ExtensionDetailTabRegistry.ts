/**
 * The `"{product_type}.{id}"` registry a `detail_tab` `ExtensionSlot`
 * resolves against — Design §3.4/§4.1's escape hatch, mirrored a third time
 * for a whole drawer tab rather than a page (`ExtensionRegistry.ts`) or a
 * table cell (`ExtensionCellRegistry.ts`). Sibling to both, not a merge into
 * either: a page extension mounts through a route with no parent row at all;
 * a cell extension renders synchronously inline in a table body; a detail-tab
 * extension owns one whole `DetailDrawerTab` body for a SINGLE selected row,
 * so it gets the same `Suspense`-lazy posture as a page slot
 * (`ExtensionSlotRenderer.tsx`) rather than the cell slot's synchronous one —
 * a drawer tab that is not the active tab pays no cost, and one that is can
 * show its own loading state without blocking the drawer chrome around it.
 *
 * `ExtensionSlot` NEVER carries code, only a name — this module is where a
 * name becomes a component, same as the page and cell registries. Production
 * entries are added by calling {@link registerDetailTabExtension} from a
 * per-product registration file imported once at app start (Nest's
 * free-prose "Health" tab is the first real case — see this slot kind's
 * module doc in `manifest.py`). The map itself names no product: onboarding
 * a new detail-tab extension is a data addition here, never a change to the
 * resolver or to `ManifestResourceDetail.tsx`, the only reader.
 */
import type { ComponentType } from "react";
import type { ExtensionSlot } from "../kit/manifestTypes";
import type { ManifestRow } from "../kit/manifestCells";

/**
 * Props every registered detail-tab extension component receives — the
 * SAME connection/tenant context `ExtensionPageProps` carries
 * (`ExtensionRegistry.ts`), plus the FULL selected row so a component can
 * render from data already fetched by the list query without a second
 * request, matching `ExtensionCellProps.row`'s own rationale. Together this
 * is enough for a component to render AND to fetch its own supplementary
 * data (e.g. Nest's Health tab querying the product's own API for a
 * database's health detail keyed off `row.id`) without the manifest or the
 * drawer host handing it anything it cannot recompute itself.
 */
export interface ExtensionDetailTabProps {
  /** e.g. `"nest"` — the same key `useProductConnection`/`useProductEnabled` use. */
  productType: string;
  /** The connected product's id for the active tenant. */
  productId: number;
  /** Active tenant id. */
  tenantId: number;
  /** The full row object for the currently-open drawer. */
  row: ManifestRow;
  /** This slot's own manifest descriptor (`id`/`label`/`resource`/`position`). */
  slot: ExtensionSlot;
}

/** The component shape a detail-tab registry entry must resolve to. */
export type ExtensionDetailTabComponent =
  ComponentType<ExtensionDetailTabProps>;

/**
 * A registry entry — the same shape a dynamic `import()` call produces, so a
 * real product entry is simply `() => import("./nest/HealthTab")` and the
 * detail host can hand it straight to `React.lazy` unchanged, matching
 * `ExtensionLoader` (`ExtensionRegistry.ts`).
 */
export type ExtensionDetailTabLoader = () => Promise<{
  default: ExtensionDetailTabComponent;
}>;

/** Composes the registry key exactly as the page and cell registries do. */
function extensionKey(productType: string, id: string): string {
  return `${productType}.${id}`;
}

const registry = new Map<string, ExtensionDetailTabLoader>();

/**
 * Registers one detail-tab-slot extension under `"{productType}.{id}"`.
 * Called once per real entry, from a product's own registration file —
 * never from `ManifestResourceDetail.tsx`, which only ever reads the
 * registry, never populates it, so the render path stays product-agnostic.
 */
export function registerDetailTabExtension(
  productType: string,
  id: string,
  loader: ExtensionDetailTabLoader,
): void {
  registry.set(extensionKey(productType, id), loader);
}

/**
 * Resolves `"{productType}.{id}"` against the detail-tab registry.
 * `undefined` means "degrade to a fallback tab body" (Design §3.4) — it is
 * never treated as an error by any caller.
 */
export function resolveDetailTabExtension(
  productType: string,
  id: string,
): ExtensionDetailTabLoader | undefined {
  return registry.get(extensionKey(productType, id));
}

/**
 * Clears every registered entry. Not called by production code — this
 * exists so tests can register a synthetic entry and guarantee it does not
 * leak into an unrelated test's assertions, matching `clearPageExtensions`/
 * `clearCellExtensions`.
 */
export function clearDetailTabExtensions(): void {
  registry.clear();
}

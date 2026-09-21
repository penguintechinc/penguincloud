/**
 * The `"{product_type}.{id}"` registry `ExtensionSlot` resolves against —
 * Design §3.4/§4.1's escape hatch. Backend contract:
 * `services/portal-api/app/adapters/manifest.py`'s `ExtensionSlot`
 * docstring — "The console resolves `"{product_type}.{id}"` against a
 * lazily-imported registry in `components/extensions/`; a slot with no
 * matching registry entry degrades to a generic fallback."
 *
 * `ExtensionSlot` NEVER carries code, only a name — this module is where a
 * name becomes a component. Production entries are added by calling
 * {@link registerPageExtension} from a per-product registration file
 * imported once at app start (none exist yet — Billing/Nest come later).
 * The map itself names no product: onboarding a new extension is a data
 * addition here, never a change to the resolver or to any routing logic
 * that reads it (`ExtensionSlotRenderer.tsx`, `ExtensionPageRoute.tsx`,
 * `extensionNav.ts`).
 */
import type { ComponentType } from "react";
import type { ExtensionSlot } from "../kit/manifestTypes";

/**
 * Props every registered page-slot extension component receives — the same
 * connection/tenant context `ProductScreen`-based screens read via
 * `useProductConnection` (`components/kit/useProductResource.ts`), so an
 * extension fetches its own data exactly like a hand-written page rather
 * than being handed pre-fetched data it cannot refresh or scope itself.
 *
 * Carries the full `ExtensionSlot` descriptor, not just its `id`, so a
 * component can read its own manifest-declared config (e.g. `slot.resource`)
 * without the manifest being re-fetched or re-parsed a second time.
 */
export interface ExtensionPageProps {
  /** e.g. `"gough"` — the same key `useProductConnection`/`useProductEnabled` use. */
  productType: string;
  /** The connected product's id for the active tenant. */
  productId: number;
  /** Active tenant id. */
  tenantId: number;
  /** This slot's own manifest descriptor (`id`/`label`/`resource`/`position`). */
  slot: ExtensionSlot;
}

/** The component shape a registry entry must resolve to. */
export type ExtensionPageComponent = ComponentType<ExtensionPageProps>;

/**
 * A registry entry — the same shape a dynamic `import()` call produces, so a
 * real product entry is simply `() => import("./gough/BillingPanel")` and
 * `ExtensionSlotRenderer` can hand it straight to `React.lazy` unchanged.
 */
export type ExtensionLoader = () => Promise<{
  default: ExtensionPageComponent;
}>;

/** Composes the registry key exactly as the backend docstring specifies. */
function extensionKey(productType: string, id: string): string {
  return `${productType}.${id}`;
}

const registry = new Map<string, ExtensionLoader>();

/**
 * Registers one page-slot extension under `"{productType}.{id}"`. Called
 * once per real entry, from a product's own registration file — never from
 * `ExtensionSlotRenderer`/`ExtensionPageRoute`, which only ever read the
 * registry, never populate it, so the render path stays product-agnostic.
 */
export function registerPageExtension(
  productType: string,
  id: string,
  loader: ExtensionLoader,
): void {
  registry.set(extensionKey(productType, id), loader);
}

/**
 * Resolves `"{productType}.{id}"` against the registry. `undefined` means
 * "degrade to the generic fallback" (Design §3.4) — it is never treated as
 * an error by any caller.
 */
export function resolveExtension(
  productType: string,
  id: string,
): ExtensionLoader | undefined {
  return registry.get(extensionKey(productType, id));
}

/**
 * Clears every registered entry. Not called by production code — the
 * registry is populated once, at module load, by each product's own
 * registration file — this exists so tests can register a synthetic entry
 * and guarantee it does not leak into an unrelated test's assertions.
 */
export function clearPageExtensions(): void {
  registry.clear();
}

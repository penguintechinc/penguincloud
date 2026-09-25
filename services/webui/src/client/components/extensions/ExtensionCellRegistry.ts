/**
 * The `"{product_type}.{id}"` registry a `cell` `ExtensionSlot` resolves
 * against — Design §3.4/§4.1's escape hatch, mirrored for a table cell
 * rather than a whole page. Sibling to `ExtensionRegistry.ts` (page slots),
 * not a merge into it: a page extension receives connection/tenant context
 * (`ExtensionPageProps`) and mounts through `React.lazy`/`Suspense`; a cell
 * extension receives one row's data (`ExtensionCellProps`) and renders
 * synchronously inline in a table body, the same posture `manifestCells.tsx`'s
 * own `CELL_REGISTRY` already takes — a per-cell Suspense boundary would
 * mean every row of every future cell extension could flash a loading state
 * independently, which no cell in this console does today.
 *
 * `ExtensionSlot` NEVER carries code, only a name — this module is where a
 * name becomes a component, same as the page registry. Production entries
 * are added by calling {@link registerCellExtension} from a per-product
 * registration file imported once at app start
 * (`components/extensions/tobogganing/register.ts` is the first). The map
 * itself names no product: onboarding a new cell override is a data
 * addition here, never a change to the resolver that reads it
 * (`ExtensionCellSlot.tsx`).
 */
import type { ComponentType } from "react";
import type { ColumnSpec } from "../kit/manifestTypes";
import type { ManifestRow } from "../kit/manifestCells";

/**
 * Props every registered cell-slot extension component receives.
 *
 * `row` is the FULL raw row object, not just this column's value — the
 * whole reason this slot kind exists is to compute a cell from a SIBLING
 * field a plain `ColumnSpec` cannot express (swg_policy's `scope_id`
 * depends on `row.scope`; see `tobogganing/manifest.py`'s
 * `_SWG_POLICY_COLUMNS` comment for the exact gap this closes). `value` is
 * `row[column.field]`, resolved the same direct way `manifestCells.tsx`'s
 * `renderCell` resolves it BEFORE applying `fallback_fields` — a cell
 * override owns its own absence handling rather than inheriting the
 * default renderer's. `column` is this slot's own `ColumnSpec` (label/cell
 * config), so a component can read its own manifest-declared config
 * without a second manifest fetch, matching `ExtensionPageProps.slot`'s
 * own rationale.
 */
export interface ExtensionCellProps {
  row: ManifestRow;
  value: unknown;
  column: ColumnSpec;
}

/** The component shape a cell registry entry must resolve to. */
export type ExtensionCellComponent = ComponentType<ExtensionCellProps>;

/** Composes the registry key exactly as `ExtensionRegistry.ts`'s page
 * registry does — a `cell` slot's `id` already IS the overridden column's
 * field name (the targeting convention `ExtensionCellSlot.tsx` matches
 * against), so no separate resource segment is needed in the key itself:
 * Design §4.1's <=2-slots-per-product budget makes a same-`id` collision
 * across two DIFFERENT resources on the same product a live risk only at a
 * scale this budget does not yet allow. */
function extensionKey(productType: string, id: string): string {
  return `${productType}.${id}`;
}

const registry = new Map<string, ExtensionCellComponent>();

/**
 * Registers one cell-slot extension under `"{productType}.{id}"`. Called
 * once per real entry, from a product's own registration file — never from
 * `ExtensionCellSlot.tsx`, which only ever reads the registry, never
 * populates it, so the render path stays product-agnostic.
 */
export function registerCellExtension(
  productType: string,
  id: string,
  component: ExtensionCellComponent,
): void {
  registry.set(extensionKey(productType, id), component);
}

/**
 * Resolves `"{productType}.{id}"` against the cell registry. `undefined`
 * means "degrade to the default `renderCell` output" (Design §3.4) — it is
 * never treated as an error by any caller.
 */
export function resolveCellExtension(
  productType: string,
  id: string,
): ExtensionCellComponent | undefined {
  return registry.get(extensionKey(productType, id));
}

/**
 * Clears every registered entry. Not called by production code — this
 * exists so tests can register a synthetic entry and guarantee it does not
 * leak into an unrelated test's assertions, matching
 * `ExtensionRegistry.ts`'s `clearPageExtensions`.
 */
export function clearCellExtensions(): void {
  registry.clear();
}

import { renderCell, type ManifestRow } from "../kit/manifestCells";
import type { ColumnSpec, ExtensionSlot } from "../kit/manifestTypes";
import { resolveCellExtension } from "./ExtensionCellRegistry";
import type { ReactNode } from "react";

/**
 * The cell-slot lookup + render decision, in isolation from `ManifestResourceScreen`'s
 * column building: given a manifest's declared `extensions`, the resource kind and
 * column a table is about to render, and the row itself, either render a registered
 * `cell`-slot extension component or degrade to the ordinary `renderCell` output —
 * Design §3.4/§4.1's escape hatch, its first real product use. Nothing here names a
 * product: the same function called with any `productType`/`extensions`/resource-kind
 * combination is the whole mechanism, matching `ExtensionSlotRenderer.tsx`'s own
 * "nothing here names a product" discipline for page slots.
 *
 * Targeting convention: a `cell` `ExtensionSlot` names the resource kind it overrides
 * in `resource` and the column it overrides in `id` (the field name) — set once,
 * declaratively, in the product's own `manifest.py` (see
 * `tobogganing/manifest.py`'s `_SWG_POLICY_COLUMNS` comment for the swg_policy
 * `scope_id` case this closes). A column with no matching declared slot renders
 * exactly as it always has; a column WITH a matching slot but no registered
 * component (declared, not yet shipped) degrades to the same default `renderCell`
 * output rather than a blank cell — "silence must never read as success" applies to
 * a single cell exactly as it does to a whole page.
 */
export function renderCellSlot(
  productType: string,
  extensions: readonly ExtensionSlot[],
  resourceKind: string,
  column: ColumnSpec,
  row: ManifestRow,
): ReactNode {
  const slot = extensions.find(
    (candidate) =>
      candidate.slot === "cell" &&
      candidate.resource === resourceKind &&
      candidate.id === column.field,
  );
  if (!slot) return renderCell(column, row);

  const CellComponent = resolveCellExtension(productType, slot.id);
  if (!CellComponent) return renderCell(column, row);

  return <CellComponent row={row} value={row[column.field]} column={column} />;
}

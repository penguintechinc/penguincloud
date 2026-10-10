/**
 * Nest's Health `detail_tab` `ExtensionSlot` — Phase 8 Nest convergence.
 *
 * Adapted from the hand-written `pages/products/nest/DatabaseTabs.tsx`'s
 * `"health"` tab, whose own doc explains why it is a separate tab rather
 * than a few lines in Overview: `healthMessage` is free prose from the last
 * probe and can be long, and inlining it would push the identifying facts
 * off the top of the drawer. `DatabaseTabs.tsx` stays uncommitted from the
 * manifest drawer's tab set (`ManifestResourceDetail.tsx` derives Overview
 * from `columns` and appends this slot itself) but is NOT deleted here —
 * kept only as the adaptation source until a later convergence stage proves
 * equivalence and removes it.
 *
 * `row` is the FULL raw manifest row (`ManifestRow` — `Record<string,
 * unknown>`, the byte proxy's wire shape, `manifestCells.tsx`), not a typed
 * `NestDatabase` — this is what every other detail-tab/cell extension reads
 * from too (`ExtensionDetailTabProps.row`, `ExtensionCellProps.row`), so
 * field access here goes through {@link asText} rather than a typed getter.
 * Field names are Nest's own raw wire keys, matching
 * `adapters/nest/manifest.py`'s own column-naming convention for this
 * resource: `healthState`, `healthMessage`, `healthLastCheck`,
 * `externalProvider`, `externalEndpoint`, `externalRegion`.
 */
import { FactList } from "../../kit";
import type { ExtensionDetailTabProps } from "../ExtensionDetailTabRegistry";

/**
 * Reads one field off the raw manifest row as display text, or `null` when
 * absent — `FactList` renders `null`/undefined as a dash, never blank, so
 * this only needs to stop `undefined`/`null` from becoming the literal
 * string `"undefined"`/`"null"`.
 */
function asText(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

export default function DatabaseHealthTab({ row }: ExtensionDetailTabProps) {
  return (
    <FactList
      testId="nest-health-facts"
      facts={[
        ["State", asText(row.healthState)],
        ["Message", asText(row.healthMessage)],
        ["Last checked", asText(row.healthLastCheck)],
        ["External provider", asText(row.externalProvider)],
        ["External endpoint", asText(row.externalEndpoint)],
        ["External region", asText(row.externalRegion)],
      ]}
    />
  );
}

import type { ExtensionCellProps } from "../ExtensionCellRegistry";

/**
 * `swg_policy`'s `scope_id` cell — the `cell` `ExtensionSlot`'s first real
 * product use, closing the one hand-transcribed equivalence gap
 * `tobogganing/manifest.py`'s `_SWG_POLICY_COLUMNS` comment names: a plain
 * `ColumnSpec` binds one field to one cell and cannot compute "Everyone"
 * from a SIBLING field (`row.scope`).
 *
 * Byte-matches the deleted `swgPolicyColumns.tsx`'s own `scope_id` render —
 * `scope_id` is null for a tenant-wide policy, and that is "Everyone", not
 * a dash: a tenant-scoped policy has no subject BY DEFINITION and applies
 * to every user, the opposite reading a blank/dash would give.
 */
export function SwgPolicyScopeCell({ row, value }: ExtensionCellProps) {
  return value ? (
    String(value)
  ) : row.scope === "tenant" ? (
    <span className="text-slate-300">Everyone</span>
  ) : (
    <span className="text-slate-500">—</span>
  );
}

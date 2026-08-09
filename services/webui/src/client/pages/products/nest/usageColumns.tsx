import type { ColumnConfig } from "../../../components/kit";
import type { NestUsageRow } from "./types";

const absent = <span className="text-slate-500">—</span>;

/**
 * Render a money value.
 *
 * `toFixed(2)` rather than `Intl.NumberFormat` with a currency: the
 * cost-calculator publishes `totalCostUsd` as a bare number and names the
 * currency only in the field name, so formatting it as a localised currency
 * would attach a symbol the product never asserted. The column header carries
 * the unit instead.
 */
function money(value: unknown): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value.toFixed(2);
}

/** Token counts are whole units; thousands separators make them readable. */
function tokens(value: unknown): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value.toLocaleString();
}

/**
 * Columns for the monthly usage table.
 *
 * `breakdown` is rendered as a count of metered resource types rather than
 * inlined: it is an open map keyed by resource type, so a column per key would
 * change shape whenever a tenant starts using a new one. The per-type figures
 * are in the detail row below the table.
 */
export const usageColumns: ColumnConfig<NestUsageRow>[] = [
  { key: "month", label: "Month" },
  {
    key: "totalTokens",
    label: "Metered units",
    render: (value) => tokens(value) ?? absent,
  },
  {
    key: "totalCostUsd",
    label: "Cost (USD)",
    render: (value) => money(value) ?? absent,
  },
  {
    key: "breakdown",
    label: "Resource types",
    render: (value) =>
      value && typeof value === "object"
        ? String(Object.keys(value).length)
        : absent,
  },
  {
    key: "updatedAt",
    label: "Updated",
    render: (value) => (value ? String(value) : absent),
  },
];

export { money, tokens };

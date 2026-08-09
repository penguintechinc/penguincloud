import { money, tokens } from "./usageColumns";
import type { NestCostSummary, NestUsageRecord } from "./types";

interface BillingSummaryProps {
  summary: NestCostSummary | null;
  isLoading: boolean;
  isUnavailable: boolean;
}

/** One headline figure. */
function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-slate-700 rounded p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-xl font-semibold text-amber-400">{value}</p>
    </div>
  );
}

/**
 * Headline totals across every metered month.
 *
 * Read from the product's own `/cost-report/summary` rather than summed from
 * the table below. The table is what the calculator returned for this request
 * and is not guaranteed to be every month it holds, so adding the visible rows
 * would render a partial figure as a total — the same class of mistake as
 * counting a paginated list to get a fleet size.
 */
export function BillingSummary({
  summary,
  isLoading,
  isUnavailable,
}: BillingSummaryProps) {
  if (isLoading) {
    return (
      <div
        className="animate-pulse h-24 bg-slate-700 rounded mb-6"
        data-testid="nest-billing-summary-loading"
      />
    );
  }

  // A missing summary is not zero. Rendering "0.00" for an absent figure
  // states a bill the product never reported.
  if (isUnavailable || !summary) {
    return (
      <p
        className="text-sm text-slate-400 mb-6"
        data-testid="nest-billing-summary-absent"
      >
        No aggregate figures were reported for this tenant.
      </p>
    );
  }

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6"
      data-testid="nest-billing-summary"
    >
      <Tile
        label="Total cost (USD)"
        value={money(summary.totalCostUsd) ?? "—"}
      />
      <Tile label="Metered units" value={tokens(summary.totalTokens) ?? "—"} />
      <Tile
        label="Months billed"
        value={
          typeof summary.months === "number" ? String(summary.months) : "—"
        }
      />
    </div>
  );
}

/**
 * Per-resource-type figures for each month.
 *
 * Rendered below the table rather than as columns because `breakdown` is an
 * open map keyed by resource type — a column per key would change the table's
 * shape whenever a tenant starts using a new one.
 */
export function UsageBreakdown({ records }: { records: NestUsageRecord[] }) {
  const withBreakdown = records.filter(
    (record) => record.breakdown && Object.keys(record.breakdown).length > 0,
  );
  if (withBreakdown.length === 0) return null;

  return (
    <section className="mt-6" data-testid="nest-usage-breakdown">
      <h2 className="text-sm font-semibold text-amber-500 mb-2">
        Usage by resource type
      </h2>
      <div className="space-y-3">
        {withBreakdown.map((record) => (
          <div
            key={record.month}
            className="border border-slate-700 rounded p-3"
            data-testid={`nest-usage-breakdown-${record.month}`}
          >
            <p className="text-sm text-slate-200 mb-1">{record.month}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {Object.entries(record.breakdown ?? {}).map(([kind, value]) => (
                <div key={kind} className="contents">
                  <dt className="text-slate-400">{kind}</dt>
                  <dd className="text-slate-200">
                    {tokens(value) ?? String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}

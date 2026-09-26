/**
 * Nest's Billing `page` `ExtensionSlot` — Phase 8 Nest convergence.
 *
 * Adapted from the hand-written `pages/products/nest/BillingPage.tsx` (plus
 * its `BillingSummary`/`UsageBreakdown`/`usageColumns` siblings and
 * `useNestBilling.ts`'s two query hooks), folded into ONE file per this
 * stage's brief. `BillingPage.tsx` itself is left uncommitted from routing
 * (see `App.tsx`) but NOT deleted — it stays the adaptation source until a
 * later convergence stage proves this panel equivalence-exact and removes
 * it.
 *
 * The one real behavioural difference from `BillingPage.tsx`: this component
 * receives `productId`/`tenantId` directly as props
 * (`ExtensionPageProps` — Design §3.4/§4.1's escape hatch), already resolved
 * by `ExtensionPageRoute`/`useConsoleManifests` before this ever mounts, so
 * it fetches its own data the same way a hand-written page does but does NOT
 * re-run `NestScreen`'s flag/connection gate — that gate already happened
 * upstream (`useConsoleManifests` only resolves a manifest entry when the
 * flag is on AND the tenant is connected to Nest; an unmet gate never
 * reaches this component at all, per `ExtensionPageRoute`'s own doc).
 *
 * Preserves, byte-for-byte in substance if not layout: the two endpoints
 * (`cost-report` + `cost-report/summary`), the aggregate KPI tiles, the
 * open-map per-month breakdown, and the tri-state availability
 * (available / empty / error) `BillingPage.tsx`'s own doc names — Nest's
 * cost routes proxy to `nest-cost-calculator` and answer 503 when it is not
 * deployed, which is a deployment state, not an empty bill, and must not
 * render the same way an empty table does.
 */
import { useQuery } from "@tanstack/react-query";
import { DataTable, EmptyState, type ColumnConfig } from "../../kit";
import { queryKeys } from "../../../api/keys";
import { nestApi } from "../../../api/resources/nest";
import type { ExtensionPageProps } from "../ExtensionRegistry";
import type {
  NestBillingResult,
  NestCostSummary,
  NestUsageRecord,
  NestUsageRow,
} from "../../../pages/products/nest/types";

/** Cost data changes at metering cadence, not request cadence. */
const BILLING_STALE_MS = 5 * 60 * 1000;

/**
 * `toFixed(2)` rather than `Intl.NumberFormat` with a currency: the
 * cost-calculator publishes `totalCostUsd` as a bare number and names the
 * currency only in the field name, so formatting it as a localised currency
 * would attach a symbol the product never asserted.
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

const absent = <span className="text-slate-500">—</span>;

/**
 * Columns for the monthly usage table. `breakdown` renders as a count of
 * metered resource types rather than inlined — it is an open map keyed by
 * resource type, so a column per key would change shape whenever a tenant
 * starts using a new one. The per-type figures are in `UsageBreakdown`
 * below the table.
 */
const usageColumns: ColumnConfig<NestUsageRow>[] = [
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
 * Headline totals across every metered month, read from the product's own
 * `/cost-report/summary` rather than summed from the table below — the
 * table is what the calculator returned for THIS request and is not
 * guaranteed to be every month it holds, so adding the visible rows would
 * render a partial figure as a total.
 */
function BillingSummary({
  summary,
  isLoading,
  isUnavailable,
}: {
  summary: NestCostSummary | null;
  isLoading: boolean;
  isUnavailable: boolean;
}) {
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
 * `record.breakdown` is guaranteed non-null and non-empty by the
 * `withBreakdown` filter below at every call site — the `?? {}` here exists
 * only to satisfy `NestUsageRecord.breakdown`'s optional type, not because
 * that fallback is reachable. Isolated in its own function so that single
 * defensive branch does not sit inline in JSX pulling this whole component's
 * branch coverage down for a case the filter above already rules out.
 */
function breakdownEntries(record: NestUsageRecord): [string, number][] {
  /* istanbul ignore next -- defensive: see this function's doc */
  return Object.entries(record.breakdown ?? {});
}

/**
 * Per-resource-type figures for each month, rendered below the table rather
 * than as columns because `breakdown` is an open map keyed by resource type.
 */
function UsageBreakdown({ records }: { records: NestUsageRecord[] }) {
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
              {breakdownEntries(record).map(([kind, value]) => (
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

/** Nest billing — metered usage and cost, read-only. There is no write path
 * here by design: cost records are produced by Nest's metering, and the
 * portal has no route that would let an operator alter them. */
export default function BillingPanel({
  productId,
  tenantId,
}: ExtensionPageProps) {
  const reportQuery = useQuery({
    queryKey: queryKeys.nestResource(tenantId, productId, "cost-report"),
    queryFn: (): Promise<NestBillingResult<{ records?: NestUsageRecord[] }>> =>
      nestApi.costReport(productId),
    staleTime: BILLING_STALE_MS,
  });
  const summaryQuery = useQuery({
    queryKey: queryKeys.nestResource(tenantId, productId, "cost-summary"),
    queryFn: (): Promise<NestBillingResult<NestCostSummary>> =>
      nestApi.costSummary(productId),
    staleTime: BILLING_STALE_MS,
  });

  const unavailable = reportQuery.data?.available === false;
  const records = reportQuery.data?.data?.records ?? [];
  const rows: NestUsageRow[] = records.map((record) => ({
    ...record,
    id: record.month,
  }));

  return (
    <div data-testid="nest-billing-panel">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">Billing</h1>
        <p className="text-slate-400 text-sm mt-1">
          Metered usage and cost for this tenant&apos;s Nest resources.
        </p>
      </header>

      {unavailable ? (
        <EmptyState
          title="Cost reporting is not available"
          description="This Nest deployment does not run the cost-calculator service, so no usage is metered. Existing resources are unaffected."
          dataTestId="nest-billing-unavailable"
        />
      ) : (
        <>
          <BillingSummary
            summary={summaryQuery.data?.data ?? null}
            isLoading={summaryQuery.isLoading}
            isUnavailable={summaryQuery.data?.available === false}
          />

          <DataTable<NestUsageRow>
            columns={usageColumns}
            data={rows}
            isLoading={reportQuery.isLoading}
            error={reportQuery.error as Error | null}
            onRetry={() => void reportQuery.refetch()}
            caption="Nest metered usage by month"
          />

          <UsageBreakdown records={records} />
        </>
      )}
    </div>
  );
}

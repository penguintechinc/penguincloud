import { EmptyState, DataTable } from "../../../components/kit";
import { NestScreen } from "./NestScreen";
import { BillingSummary, UsageBreakdown } from "./BillingSummary";
import { usageColumns } from "./usageColumns";
import { useNestCostReport, useNestCostSummary } from "./useNestBilling";
import type { NestUsageRow } from "./types";

/**
 * Nest billing — metered usage and cost, read-only.
 *
 * There is no write path here by design: cost records are produced by Nest's
 * metering, and the portal has no route that would let an operator alter them.
 *
 * The screen's one subtlety is that "no data" has two meanings and they must
 * not render alike. Nest's cost routes proxy to `nest-cost-calculator` and
 * answer 503 when it is not deployed; showing that as an empty table would
 * tell an operator they were billed nothing, which is a different and much
 * worse claim than "this deployment does not meter".
 */
export default function BillingPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useNestCostReport();
  const summary = useNestCostSummary();

  const unavailable = data?.available === false;
  const records = data?.data?.records ?? [];
  const rows: NestUsageRow[] = records.map((record) => ({
    ...record,
    id: record.month,
  }));

  return (
    <NestScreen
      title="Billing"
      description="Metered usage and cost for this tenant's Nest resources."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      {unavailable ? (
        <EmptyState
          title="Cost reporting is not available"
          description="This Nest deployment does not run the cost-calculator service, so no usage is metered. Existing resources are unaffected."
          dataTestId="nest-billing-unavailable"
        />
      ) : (
        <>
          <BillingSummary
            summary={summary.data?.data ?? null}
            isLoading={summary.isLoading}
            isUnavailable={summary.data?.available === false}
          />

          <DataTable<NestUsageRow>
            columns={usageColumns}
            data={rows}
            isLoading={isLoading}
            error={error as Error | null}
            onRetry={() => void refetch()}
            caption="Nest metered usage by month"
          />

          <UsageBreakdown records={records} />
        </>
      )}
    </NestScreen>
  );
}

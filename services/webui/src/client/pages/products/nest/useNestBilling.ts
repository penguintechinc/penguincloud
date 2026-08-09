/**
 * Billing queries for the Nest cost screens.
 *
 * Separate from `useNest.ts` because billing is not a resource listing and does
 * not share its failure model: Nest's cost routes proxy to
 * `nest-cost-calculator`, and answer 503 when that service is not deployed.
 * That is a normal deployment state, not a fault of the request, so the
 * bindings map it to `available: false` rather than throwing — and these hooks
 * pass it through instead of collapsing it into an error or an empty list.
 *
 * Both gates that apply to every Nest screen apply here too: the feature flag
 * gates the FETCH via `useNestConnection`, not just the render.
 */

import { useQuery } from "@tanstack/react-query";
import { nestApi } from "../../../api/resources/nest";
import { queryKeys } from "../../../api/keys";
import { useNestConnection } from "./useNest";
import type {
  NestBillingResult,
  NestCostSummary,
  NestUsageRecord,
} from "./types";

/** Cost data changes at metering cadence, not request cadence. */
const BILLING_STALE_MS = 5 * 60 * 1000;

/** Monthly usage records for the tenant. */
export function useNestCostReport() {
  const { tenantId, productId, isLoading, isEnabled } = useNestConnection();

  const query = useQuery({
    queryKey: queryKeys.nestResource(tenantId, productId, "cost-report"),
    queryFn: async (): Promise<
      NestBillingResult<{ records?: NestUsageRecord[] }>
    > => {
      if (productId === undefined) return { available: false, data: null };
      return nestApi.costReport(productId);
    },
    enabled: isEnabled && productId !== undefined,
    staleTime: BILLING_STALE_MS,
  });

  return { ...query, productId, isConnectionLoading: isLoading };
}

/** Aggregate across every month the calculator holds. */
export function useNestCostSummary() {
  const { tenantId, productId, isEnabled } = useNestConnection();

  return useQuery({
    queryKey: queryKeys.nestResource(tenantId, productId, "cost-summary"),
    queryFn: async (): Promise<NestBillingResult<NestCostSummary>> => {
      if (productId === undefined) return { available: false, data: null };
      return nestApi.costSummary(productId);
    },
    enabled: isEnabled && productId !== undefined,
    staleTime: BILLING_STALE_MS,
  });
}

/**
 * Operation polling hooks for the Gough screens.
 *
 * Split from `useGough.ts` so the resource hooks and the poll loop stay
 * separately readable — the polling rules below are the subtle part and are
 * easy to lose at the bottom of a longer module.
 *
 * Every loop stops on `is_terminal`, which the portal publishes for exactly
 * this purpose. Branching on a status string instead means re-implementing
 * the terminal-state set in the client, and getting one state wrong there
 * freezes the UI on a stale frame that never corrects itself.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { goughOperationsApi } from "../../../api/resources/goughOperations";
import { queryKeys } from "../../../api/keys";
import { useGoughConnection } from "./useGough";
import type {
  GoughMetricsSummary,
  GoughOperation,
  GoughOperationLogLine,
} from "./types";

/** Poll interval for a live operation. */
const OPERATION_POLL_MS = 3000;

/**
 * Operations the product is currently running.
 *
 * Polls while any operation is live and stops once they are all terminal —
 * `is_terminal` is published by the portal precisely so the client does not
 * re-implement the terminal-state set (and get it wrong for one state).
 */
export function useGoughOperations() {
  const { tenantId, productId, isEnabled } = useGoughConnection();

  return useQuery({
    queryKey: queryKeys.goughOperations(tenantId, productId),
    queryFn: async (): Promise<GoughOperation[]> => {
      if (productId === undefined) return [];
      return goughOperationsApi.listOperations(productId);
    },
    enabled: isEnabled && productId !== undefined,
    refetchInterval: (query) => {
      const rows = query.state.data;
      if (!rows || rows.length === 0) return false;
      return rows.some((item) => !item.is_terminal) ? OPERATION_POLL_MS : false;
    },
  });
}

/**
 * Log lines for one operation, polled while it is still live.
 *
 * `enabled` is what makes the disclosure cheap: the query does not run until
 * the operator actually opens the log view, so a panel listing ten
 * deployments does not fetch ten log streams nobody asked for.
 *
 * Polling stops on `is_terminal` for the same reason every other loop here
 * does — a finished operation's log will not grow, and a loop that keeps
 * asking is pure background traffic.
 */
export function useOperationLogs(
  kind: string,
  operationId: string,
  options: { enabled: boolean; isTerminal: boolean },
) {
  const { tenantId, productId, isEnabled } = useGoughConnection();

  return useQuery({
    queryKey: queryKeys.goughOperationLogs(
      tenantId,
      productId,
      kind,
      operationId,
    ),
    queryFn: async (): Promise<GoughOperationLogLine[]> => {
      if (productId === undefined) return [];
      return goughOperationsApi.operationLogs(productId, kind, operationId);
    },
    enabled: isEnabled && productId !== undefined && options.enabled,
    refetchInterval: options.isTerminal ? false : OPERATION_POLL_MS,
  });
}

/**
 * Headline metrics for the tenant's Gough connection.
 *
 * The dashboard card reads `totals` from here rather than counting rows in the
 * node/agent lists. Those lists are paginated, so their length is a page size,
 * not a fleet size — a tenant with more nodes than one page would have seen a
 * confidently wrong number.
 */
export function useGoughMetrics() {
  const { tenantId, productId, isEnabled } = useGoughConnection();

  return useQuery({
    queryKey: queryKeys.goughMetrics(tenantId, productId),
    queryFn: async (): Promise<GoughMetricsSummary | null> => {
      if (productId === undefined) return null;
      return goughOperationsApi.metricsSummary(productId);
    },
    enabled: isEnabled && productId !== undefined,
  });
}

/** Requests cancellation of a live operation. */
export function useCancelOperation() {
  const queryClient = useQueryClient();
  const { tenantId, productId, isEnabled } = useGoughConnection();

  return useMutation({
    mutationFn: async (vars: {
      kind: string;
      operationId: string;
    }): Promise<unknown> => {
      if (!isEnabled || productId === undefined) {
        throw new Error("No Gough connection for the active tenant");
      }
      return goughOperationsApi.cancelOperation(
        productId,
        vars.kind,
        vars.operationId,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.goughOperations(tenantId, productId),
      });
    },
  });
}

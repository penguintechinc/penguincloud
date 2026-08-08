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
import type { GoughOperation } from "./types";

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
 * Polls a single operation until it reaches a terminal state.
 *
 * The poll stops on `is_terminal` rather than on a status string, so an
 * unrecognised Gough status keeps the loop alive instead of freezing the UI
 * on a stale frame that never corrects itself.
 */
export function useGoughOperation(
  kind: string | undefined,
  operationId: string | undefined,
) {
  const { tenantId, productId, isEnabled } = useGoughConnection();
  const enabled =
    isEnabled &&
    productId !== undefined &&
    Boolean(kind) &&
    Boolean(operationId);

  return useQuery({
    queryKey: queryKeys.goughOperation(
      tenantId,
      productId,
      kind ?? "",
      operationId ?? "",
    ),
    queryFn: async (): Promise<GoughOperation | null> => {
      if (productId === undefined || !kind || !operationId) return null;
      return goughOperationsApi.getOperation(productId, kind, operationId);
    },
    enabled,
    refetchInterval: (query) =>
      query.state.data && !query.state.data.is_terminal
        ? OPERATION_POLL_MS
        : false,
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

/**
 * Generic operations polling, cancel, and log-fetch for a manifest-driven
 * product screen.
 *
 * Unlike list resources (proxied, product-specific paths declared per
 * `ResourceDescriptor.list`), every operations route here is a single
 * portal-owned typed route — `GET /api/v1/products/{product_id}/operations`,
 * `POST .../operations/{kind}/{id}/cancel`, `GET .../operations/{kind}/{id}/
 * logs` — identical for every product (`portalUrl.*`, already used by
 * `pages/products/gough/useGoughOperations.ts`). That is what makes every
 * hook in this module product-agnostic: nothing about any of them is
 * Gough-specific, or needs to be.
 *
 * Schema v2 closes the gap this module's docstring used to name here:
 * `OperationsSpec` now carries `cancel_allowed`/`show_logs`
 * (`manifestTypes.ts`), matching `operationsPanelTypes.ts`'s
 * `OperationsPanelSpec` field for field, so `ManifestResourceScreen` can
 * wire a REAL cancel control and log disclosure instead of always rendering
 * read-only.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import api from "../../lib/api";
import { portalUrl } from "../../api/portalPaths";
import { envelopeList } from "../../api/envelope";
import { queryKeys } from "../../api/keys";
import type { OperationLike, OperationLogLine } from "./operationsPanelTypes";

/**
 * The polling decision, factored out of the `useQuery` options so it is
 * directly unit-testable rather than only reachable through TanStack
 * Query's own internals. Mirrors `useGoughOperations`'s own
 * `refetchInterval` logic, generalised off the manifest's own declared poll
 * interval instead of a hardcoded constant.
 */
export function nextPollInterval(
  rows: OperationLike[] | undefined,
  pollIntervalMs: number,
): number | false {
  if (!rows || rows.length === 0) return false;
  return rows.some((item) => !item.is_terminal) ? pollIntervalMs : false;
}

/**
 * Live operations for one product connection, polled while any is
 * non-terminal.
 */
export function useManifestOperations(
  tenantId: number | undefined,
  productId: number | undefined,
  enabled: boolean,
  pollIntervalMs: number,
): UseQueryResult<OperationLike[]> {
  return useQuery({
    queryKey: queryKeys.consoleManifestOperations(tenantId, productId),
    queryFn: async (): Promise<OperationLike[]> => {
      /* istanbul ignore next -- defensive: `enabled` requires productId to be
         defined before queryFn ever runs; this keeps queryFn total for the
         type checker rather than asserting past it. */
      if (productId === undefined) return [];
      const response = await api.get(portalUrl.operations(productId));
      return envelopeList<OperationLike>(response.data, "operations");
    },
    enabled: enabled && productId !== undefined,
    refetchInterval: (query) =>
      nextPollInterval(query.state.data, pollIntervalMs),
  });
}

/**
 * Requests cancellation of a live operation via `POST
 * /products/{id}/operations/{kind}/{id}/cancel`. Only ever invoked when the
 * manifest's `operations.cancel_allowed` is true — `ManifestResourceScreen`
 * gates the control on it, and `validate_manifest`'s
 * `supports_cancel`/`operations.cancel_allowed` check refuses a manifest
 * that claims the capability without the adapter actually offering it (see
 * `OperationsSpec`'s Python doc).
 */
export function useCancelManifestOperation(
  tenantId: number | undefined,
  productId: number | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      kind: string;
      operationId: string;
    }): Promise<unknown> => {
      if (productId === undefined) {
        throw new Error("No connection for the active tenant");
      }
      const response = await api.post(
        portalUrl.cancelOperation(productId, vars.kind, vars.operationId),
      );
      return response.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.consoleManifestOperations(tenantId, productId),
      });
    },
  });
}

/**
 * Log lines for one operation, polled while it is still live — mounted only
 * while an operator has a row's logs open (`OperationsPanel.tsx`'s own
 * `OperationLogsSection`), so a settled panel costs zero log requests. Only
 * ever wired when the manifest's `operations.show_logs` is true.
 */
export function useManifestOperationLogs(
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
  operationId: string,
  options: { enabled: boolean; isTerminal: boolean },
): UseQueryResult<OperationLogLine[]> {
  const OPERATION_LOGS_POLL_MS = 3000;
  return useQuery({
    queryKey: queryKeys.consoleManifestOperationLogs(
      tenantId,
      productId,
      kind,
      operationId,
    ),
    queryFn: async (): Promise<OperationLogLine[]> => {
      /* istanbul ignore next -- defensive: `enabled` requires productId to be
         defined before queryFn ever runs; this keeps queryFn total for the
         type checker rather than asserting past it. */
      if (productId === undefined) return [];
      const response = await api.get(
        portalUrl.operationLogs(productId, kind, operationId),
      );
      return envelopeList<OperationLogLine>(response.data, "logs");
    },
    enabled: options.enabled && productId !== undefined,
    refetchInterval: options.isTerminal ? false : OPERATION_LOGS_POLL_MS,
  });
}

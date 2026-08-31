/**
 * Generic operations polling for a manifest-driven product screen.
 *
 * Unlike list resources (proxied, product-specific paths declared per
 * `ResourceDescriptor.list`), the operations LIST endpoint is a single
 * portal-owned typed route — `GET /api/v1/products/{product_id}/operations`
 * — identical for every product (`portalUrl.operations`, already used by
 * `pages/products/gough/useGoughOperations.ts`). That is what makes this
 * hook product-agnostic: nothing about it is Gough-specific, or needs to be.
 *
 * Schema gap this hook works around by omission, not invention:
 * `OperationsSpec` (`manifestTypes.ts`) carries only `label` and
 * `poll_interval_seconds` — no `cancelAllowed`/`showLogs` fields
 * `components/kit/operationsPanelTypes.ts`'s `OperationsPanelSpec` needs.
 * A manifest cannot currently express "this product's operations support
 * cancel" or "...support a log stream", so `ManifestResourceScreen` renders
 * a READ-ONLY panel (`cancelAllowed: false`, `showLogs: false`) rather than
 * guessing. See the Step 3 report for this named precisely.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import api from "../../lib/api";
import { portalUrl } from "../../api/portalPaths";
import { envelopeList } from "../../api/envelope";
import { queryKeys } from "../../api/keys";
import type { OperationLike } from "./operationsPanelTypes";

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

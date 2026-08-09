/**
 * The portal's own operation endpoints for a Gough connection.
 *
 * Separate from `gough.ts` because these are a different path with different
 * trust properties: resources go through the PROXY (caller-supplied paths,
 * governed by the RouteRule allowlist), while operations are typed portal
 * routes backed by the adapter's list/get/cancel/logs methods. Keeping them
 * in one module invites a future call site treating the two as
 * interchangeable.
 */

import api from "../../lib/api";
import { envelopeList } from "../envelope";
import { portalUrl } from "../portalPaths";
import type {
  GoughActionResult,
  GoughMetricsSummary,
  GoughOperation,
  GoughOperationLogLine,
} from "../../pages/products/gough/types";

export const goughOperationsApi = {
  /** Headline metrics for the connection — the product's own scrape. */
  metricsSummary: async (productId: number): Promise<GoughMetricsSummary> => {
    const response = await api.get(portalUrl.metrics(productId));
    return response.data as GoughMetricsSummary;
  },

  /**
   * Invoke a product action through the TYPED portal route.
   *
   * Not `proxyApi`, and that is the point. Proxying `POST /nodes/{id}/deploy`
   * forwards Gough's raw 202 to the browser: no normalised state, no poll key,
   * so the caller can only invalidate its queries and hope the deploy it
   * started shows up. This route returns an `ActionResult`, so the caller
   * learns the ids of the deployments it just started and can poll each one.
   *
   * See "Which mutations go through which path" in `app/adapters/base.py`.
   */
  performAction: async (
    productId: number,
    kind: string,
    resourceId: string,
    action: string,
    payload?: Record<string, unknown>,
  ): Promise<GoughActionResult> => {
    const response = await api.post(
      portalUrl.resourceAction(productId, kind, resourceId, action),
      payload ?? {},
    );
    return response.data as GoughActionResult;
  },

  /**
   * Operations the product is currently running. Portal endpoint, not proxy.
   *
   * `operations` is a required field of `OperationListResponse`, so an empty
   * page arrives as `{"operations": []}` and its absence cannot mean "none" —
   * see `envelopeList`. Reporting none is the same false statement that
   * shipped for Nest's snapshots.
   */
  listOperations: async (productId: number): Promise<GoughOperation[]> => {
    const response = await api.get(portalUrl.operations(productId));
    return envelopeList<GoughOperation>(response.data, "operations");
  },

  /** Poll one operation. `kind` selects the poll route; both are path segments. */
  getOperation: async (
    productId: number,
    kind: string,
    operationId: string,
  ): Promise<GoughOperation> => {
    const response = await api.get(
      portalUrl.operation(productId, kind, operationId),
    );
    return response.data as GoughOperation;
  },

  cancelOperation: async (
    productId: number,
    kind: string,
    operationId: string,
  ): Promise<unknown> => {
    const response = await api.post(
      portalUrl.cancelOperation(productId, kind, operationId),
    );
    return response.data;
  },

  /**
   * Log lines for an operation. `since` fetches only what is new, so a poll
   * loop does not re-download the whole stream on every tick.
   *
   * An operation with no output yet answers `{"logs": []}` — `logs` is a
   * required field of `OperationLogsResponse`. A missing key is a shape this
   * client does not understand, and "no output" is exactly the wrong thing to
   * tell someone watching a deploy.
   */
  operationLogs: async (
    productId: number,
    kind: string,
    operationId: string,
    since?: string,
  ): Promise<GoughOperationLogLine[]> => {
    const response = await api.get(
      portalUrl.operationLogs(productId, kind, operationId),
      { params: since ? { since } : undefined },
    );
    return envelopeList<GoughOperationLogLine>(response.data, "logs");
  },
};

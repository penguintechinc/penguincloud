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
import type {
  GoughOperation,
  GoughOperationLogLine,
} from "../../pages/products/gough/types";

/** Encoded path segment — an id never composes a new path here. */
const seg = (value: string | number): string =>
  encodeURIComponent(String(value));

export const goughOperationsApi = {
  /** Operations the product is currently running. Portal endpoint, not proxy. */
  listOperations: async (productId: number): Promise<GoughOperation[]> => {
    const response = await api.get(`/products/${productId}/operations`);
    const body = response.data as { operations?: GoughOperation[] };
    return body.operations ?? [];
  },

  /** Poll one operation. `kind` selects the poll route; both are path segments. */
  getOperation: async (
    productId: number,
    kind: string,
    operationId: string,
  ): Promise<GoughOperation> => {
    const response = await api.get(
      `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}`,
    );
    return response.data as GoughOperation;
  },

  cancelOperation: async (
    productId: number,
    kind: string,
    operationId: string,
  ): Promise<unknown> => {
    const response = await api.post(
      `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}/cancel`,
    );
    return response.data;
  },

  /**
   * Log lines for an operation. `since` fetches only what is new, so a poll
   * loop does not re-download the whole stream on every tick.
   */
  operationLogs: async (
    productId: number,
    kind: string,
    operationId: string,
    since?: string,
  ): Promise<GoughOperationLogLine[]> => {
    const response = await api.get(
      `/products/${productId}/operations/${seg(kind)}/${seg(operationId)}/logs`,
      { params: since ? { since } : undefined },
    );
    const body = response.data as { logs?: GoughOperationLogLine[] };
    return body.logs ?? [];
  },
};

/**
 * Nest WRITES and operation polling, on TYPED portal routes.
 *
 * Separate from `nest.ts` because these are a different path with different
 * trust properties: reads go through the PROXY (caller-supplied paths, governed
 * by the RouteRule allowlist), while everything here is a typed portal route
 * backed by an adapter method.
 *
 * For Nest that split is not a preference. Its allowlist is GET-only, because
 * every Nest write answers `202` with an `operationId` and `app/adapters/base.py`
 * puts any mutation whose result the portal must interpret on a typed method —
 * the proxy is a byte pipe and cannot return an `ActionResult`. Proxying a
 * create here would hand the browser a raw 202 with no poll key.
 */

import api from "../../lib/api";
import { portalUrl } from "../portalPaths";
import type {
  NestActionResult,
  NestCreatedResource,
  NestOperation,
} from "../../pages/products/nest/types";

/**
 * Portal kind for a Nest DataResource.
 *
 * `database` is the PORTAL's vocabulary, matching `KIND_DATABASE` in
 * `app/adapters/nest/mapping.py`; Nest's own name for it is DataResource. The
 * adapter validates this against a literal table, so a wrong value here is a
 * 501 rather than a request built against an unknown collection.
 */
export const NEST_KIND_DATABASE = "database";

/**
 * The single operation family Nest has.
 *
 * Every long-running Nest action — snapshot, restore, introspect, migrate, and
 * every create — is polled at the same route, so `kind` is one value rather
 * than a family per action. Matches `OP_KIND` in the adapter's mapping.
 */
export const NEST_OPERATION_KIND = "operation";

export const nestResourcesApi = {
  /** Create a data-resource. Returns the row and its poll handle. */
  createDatabase: async (
    productId: number,
    payload: Record<string, unknown>,
  ): Promise<NestCreatedResource> => {
    const response = await api.post(
      portalUrl.resources(productId, NEST_KIND_DATABASE),
      payload,
    );
    return response.data as NestCreatedResource;
  },

  /**
   * Delete a data-resource by NAME.
   *
   * Nest answers 409 when the resource is still referenced; the adapter maps
   * that to a portal 409, which is what lets the confirm dialog tell "still
   * referenced" from "already gone".
   */
  deleteDatabase: async (productId: number, name: string): Promise<unknown> => {
    const response = await api.delete(
      portalUrl.resource(productId, NEST_KIND_DATABASE, name),
    );
    return response.data;
  },

  /**
   * Start snapshot / restore / introspect / migrate on a data-resource.
   *
   * Returns the operations the action started, each already addressable at
   * `/operations/{kind}/{id}` — so the caller can follow exactly the work it
   * began rather than invalidating its queries and hoping.
   */
  performAction: async (
    productId: number,
    name: string,
    action: string,
    payload?: Record<string, unknown>,
  ): Promise<NestActionResult> => {
    const response = await api.post(
      portalUrl.resourceAction(productId, NEST_KIND_DATABASE, name, action),
      payload ?? {},
    );
    return response.data as NestActionResult;
  },

  /** Poll one operation. Nest has no list route, so ids come from actions. */
  getOperation: async (
    productId: number,
    operationId: string,
  ): Promise<NestOperation> => {
    const response = await api.get(
      portalUrl.operation(productId, NEST_OPERATION_KIND, operationId),
    );
    return response.data as NestOperation;
  },
};

/**
 * Gough resource calls, made through the portal PROXY.
 *
 * The proxy is the untrusted-input path — the caller supplies the path
 * string — so every path below is admitted by an explicit RouteRule in
 * `app/adapters/gough/routes.py`. Reads need `products:gough:read`, every
 * mutating verb `products:gough:manage`.
 *
 * A path built here must stay inside that allowlist. Ids are interpolated, so
 * they are encoded, and a value that is not id-shaped is refused by the
 * portal rather than reaching Gough — the allowlist types each id family
 * (digits for nodes/biomes, hex for agent UUIDs) precisely so a word-shaped
 * value cannot match an id slot.
 *
 * Operations live in `goughOperations.ts`: they are typed portal routes, not
 * proxied paths, and the two should not be reached for interchangeably.
 *
 * **Actions are not here.** `nodeAction`/`agentAction` used to live in this
 * module and POST through the proxy, which returned Gough's raw 202 to the
 * browser — no `ActionResult`, no normalised state, no poll key — so the UI
 * could only invalidate its queries and hope the deploy it started appeared.
 * They are now `goughOperationsApi.performAction`, on the typed route, which
 * returns the ids of the operations the action started. What is left in this
 * module is reads and plain field writes: mutations whose whole result is
 * already in the product's own response body.
 */

import { proxyApi } from "./products";
import { GOUGH_COLLECTION_PATHS } from "./goughPaths";
import type {
  GoughAgent,
  GoughBiome,
  GoughNode,
} from "../../pages/products/gough/types";

/**
 * Gough's two response shapes, unwrapped in one place.
 *
 * Enveloped `{status, data, meta}` for nodes/biomes/deployments; a bare
 * object for agents and status. This mirrors `unwrap` in
 * `app/adapters/gough/responses.py` — the same difference, handled the same
 * way, so no call site has to remember which family an endpoint belongs to.
 */
function unwrap(payload: unknown): unknown {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as { data: unknown }).data;
  }
  return payload;
}

/**
 * Pull a named array out of an unwrapped Gough list body.
 *
 * Gough keys its collections by resource name (`{"nodes": [...]}`) rather
 * than returning a bare array. Returns an empty array rather than throwing
 * when the key is absent: an empty table is a truthful rendering of "no rows
 * came back", whereas a thrown error would show a failure banner for a fleet
 * that simply has no nodes yet.
 */
function collection<T>(payload: unknown, key: string): T[] {
  const body = unwrap(payload);
  if (body && typeof body === "object" && key in body) {
    const rows = (body as Record<string, unknown>)[key];
    if (Array.isArray(rows)) return rows as T[];
  }
  return Array.isArray(body) ? (body as T[]) : [];
}

/** Encoded path segment — an id never composes a new path here. */
const seg = (value: string | number): string =>
  encodeURIComponent(String(value));

export const goughApi = {
  listNodes: async (productId: number): Promise<GoughNode[]> =>
    collection<GoughNode>(
      await proxyApi.request(productId, "GET", GOUGH_COLLECTION_PATHS.nodes),
      "nodes",
    ),

  listBiomes: async (productId: number): Promise<GoughBiome[]> =>
    collection<GoughBiome>(
      await proxyApi.request(productId, "GET", GOUGH_COLLECTION_PATHS.biomes),
      "biomes",
    ),

  listAgents: async (productId: number): Promise<GoughAgent[]> =>
    collection<GoughAgent>(
      await proxyApi.request(productId, "GET", GOUGH_COLLECTION_PATHS.agents),
      "agents",
    ),

  updateNodeTags: async (
    productId: number,
    nodeId: string,
    tags: string[],
  ): Promise<unknown> =>
    proxyApi.request(productId, "PATCH", `api/v1/nodes/${seg(nodeId)}/tags`, {
      hardware_tags: tags,
    }),

  createBiome: async (
    productId: number,
    payload: Record<string, unknown>,
  ): Promise<unknown> =>
    proxyApi.request(productId, "POST", GOUGH_COLLECTION_PATHS.biomes, payload),

  updateBiome: async (
    productId: number,
    biomeId: string,
    payload: Record<string, unknown>,
  ): Promise<unknown> =>
    proxyApi.request(
      productId,
      "PUT",
      `api/v1/biomes/${seg(biomeId)}`,
      payload,
    ),

  deleteBiome: async (productId: number, biomeId: string): Promise<unknown> =>
    proxyApi.request(productId, "DELETE", `api/v1/biomes/${seg(biomeId)}`),
};

/**
 * Turns a manifest `ListSpec` into a `useProductResource`-compatible
 * fetcher: strip the leading slash `path_bytes` carries, proxy the GET, and
 * walk the declared `EnvelopeSpec.keys` path out of whatever comes back.
 */
import { proxyApi } from "../../api/resources/products";
import type { ListSpec } from "./manifestTypes";
import type { ManifestRow } from "./manifestCells";

/**
 * `ListSpec.path_bytes` MUST start with `/` (`ListSpec.__post_init__`
 * refuses otherwise) because it is meant to be byte-equal to the adapter's
 * own registered route (e.g. `_COLLECTION_ROUTES["nodes"] ==
 * "/api/v1/nodes/"`). `proxyRequestUrl`/`proxyApi.request`, though, want the
 * PRODUCT-RELATIVE fragment with NO leading slash — `goughPaths.ts`'s own
 * `GOUGH_COLLECTION_PATHS.nodes` is `"api/v1/nodes/"`, one character
 * shorter. Handing `path_bytes` to `proxyApi.request` unmodified would
 * build `/products/{id}/proxy//api/v1/nodes/` — a double slash — which is
 * exactly the class of defect `goughPaths.ts`'s own module doc warns about
 * (a request carrying a slash Werkzeug's route does not declare 404s with
 * no redirect). Stripping exactly one leading slash reproduces
 * `goughPaths.ts`'s existing values byte-for-byte — see
 * `__tests__/manifestListFetcher.test.ts`'s "matches goughPaths.ts" case.
 *
 * Shared with `manifestItemPath.ts`, which needs the identical strip for
 * `ItemPathSpec.prefix`.
 */
export function toProxyPath(pathBytes: string): string {
  return pathBytes.startsWith("/") ? pathBytes.slice(1) : pathBytes;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Walk `payload` through `keys` in order, returning the array at the end of
 * the path — or `[]` if any step along the way is not the shape declared.
 *
 * Schema v2 closes the gap schema v1 left open (`ListSpec.envelope_key`'s
 * own docstring called itself "the ONLY declared shape a proxied read has",
 * which was not literally true of Gough's real wire responses — see
 * `EnvelopeSpec`'s doc in `manifestTypes.ts`). There is no more guessing
 * "try the top level, then one level inside `data`": `EnvelopeSpec.keys` is
 * the adapter's OWN declared path (`("data", "nodes")` for the enveloped
 * routes, bare `("agents",)` for the ones that are not), verified server-side
 * against the adapter's real wire shape by `validate_manifest`'s
 * `envelope_paths` check — so this function's only job is to follow that
 * path exactly, never to infer one.
 *
 * Still degrades to `[]` rather than throwing on a mismatch: a manifest's
 * declared envelope disagreeing with what actually arrived is a live-overlay
 * or transport failure to surface as "no rows", not a reason to crash the
 * whole screen — `useProductResource`'s own query error path already exists
 * for a genuinely failed fetch.
 */
export function readManifestEnvelope(
  payload: unknown,
  keys: readonly string[],
): ManifestRow[] {
  let cursor: unknown = payload;
  for (let i = 0; i < keys.length; i++) {
    if (!isPlainObject(cursor)) return [];
    const key = keys[i] as string;
    cursor = cursor[key];
    const isLastKey = i === keys.length - 1;
    if (isLastKey) {
      return Array.isArray(cursor) ? (cursor as ManifestRow[]) : [];
    }
  }
  return [];
}

/** Builds the `fetcher` `useProductResource` needs from one resource's `ListSpec`. */
export function buildManifestListFetcher(
  list: ListSpec,
): (productId: number) => Promise<ManifestRow[]> {
  const proxyPath = toProxyPath(list.path_bytes);
  return async (productId: number): Promise<ManifestRow[]> => {
    const payload = await proxyApi.request(productId, "GET", proxyPath);
    return readManifestEnvelope(payload, list.envelope.keys);
  };
}

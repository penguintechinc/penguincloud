/**
 * Turns a manifest `ListSpec` into a `useProductResource`-compatible
 * fetcher: strip the leading slash `path_bytes` carries, proxy the GET, and
 * read the declared envelope key out of whatever comes back.
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
 */
export function toProxyPath(pathBytes: string): string {
  return pathBytes.startsWith("/") ? pathBytes.slice(1) : pathBytes;
}

function readArrayKey(payload: unknown, key: string): ManifestRow[] | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload))
    return null;
  const rows = (payload as Record<string, unknown>)[key];
  return Array.isArray(rows) ? (rows as ManifestRow[]) : null;
}

/**
 * Read `payload[envelopeKey]`, unwrapping one optional outer `{ data: {...}
 * }` transport envelope first.
 *
 * Schema gap: `ListSpec.envelope_key`'s own docstring calls itself "the
 * ONLY declared shape a proxied read has" — that is not literally true of
 * Gough's real wire responses. Gough's `_helpers.envelope_success` routes
 * (nodes, biomes, deployments — see `app/adapters/gough/responses.py`'s
 * module doc) answer `{"status": "success", "data": {<key>: [...]},
 * "meta": {...}}`, while its older handlers (agents) answer a bare
 * `{<key>: [...]}`. Nothing in `ListSpec` declares which family a resource
 * belongs to. This generalises `api/resources/gough.ts`'s own hand-written
 * `unwrap`+`collection` pair (which independently discovered the identical
 * per-resource split) into a product-agnostic reader: try the top-level key
 * first, then one level inside `data`. See the Step 3 report for this
 * finding stated precisely — the honest fix is a field on `ListSpec`
 * (e.g. `enveloped: bool`), not a renderer guessing forever.
 */
export function readManifestEnvelope(
  payload: unknown,
  envelopeKey: string,
): ManifestRow[] {
  const direct = readArrayKey(payload, envelopeKey);
  if (direct) return direct;
  if (payload && typeof payload === "object" && "data" in payload) {
    const nested = readArrayKey(
      (payload as { data: unknown }).data,
      envelopeKey,
    );
    if (nested) return nested;
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
    return readManifestEnvelope(payload, list.envelope_key);
  };
}

/**
 * Builds one resource's item-level proxy path from its declared
 * `ItemPathSpec` — the ONE place `{prefix}/{id}` concatenation happens.
 *
 * Schema v2 finding, restated for the renderer side: a resource's item
 * route cannot be derived by string-munging `ListSpec.path_bytes` (see
 * `ItemPathSpec`'s doc in `manifestTypes.ts` for the exact
 * `/api/v1/biomes/groups` + id -> `/api/v1/biomes/groups42` defect this
 * closes). `ItemPathSpec.prefix` is the adapter's own item-route base,
 * already proven reachable by `validate_manifest`'s `sample_id` probe at
 * import time; this module only ever appends a REAL id to it.
 */
import { toProxyPath } from "./manifestListFetcher";
import type { ItemPathSpec } from "./manifestTypes";

/**
 * The item's absolute path, byte-equal to `` `${prefix}/${id}` `` per
 * `ItemPathSpec`'s own contract. `id` is taken verbatim — the caller reads
 * it off the row via the resource's own `id_field`, never a hardcoded `id`
 * key (Gough addresses agents by `agent_id`).
 */
export function manifestItemPathBytes(
  itemPath: ItemPathSpec,
  id: string,
): string {
  return `${itemPath.prefix}/${id}`;
}

/** The proxy-relative fragment for one item — `manifestItemPathBytes` with
 * the single leading slash `proxyApi.request` does not want stripped, the
 * same transform `toProxyPath` already applies to a collection path. */
export function toProxyItemPath(itemPath: ItemPathSpec, id: string): string {
  return toProxyPath(manifestItemPathBytes(itemPath, id));
}

/**
 * Tobogganing payload shapes as they arrive through the portal.
 *
 * Transcribed from the product's own list handlers, not from a spec: Session 1
 * established that Tobogganing's live `GET /openapi.json` serves a hardcoded
 * 5-path placeholder while claiming to expose "the complete API surface"
 * (`hub_api/app.py:381-397`). Field names below are the ones the handlers
 * literally emit:
 *
 * - clients — `hub_api/modules/sdwan/api/clients.py:544-554`
 * - clusters — `hub_api/modules/sdwan/api/clusters.py:253-262`
 * - peers — `hub_api/modules/sdwan/certs/wireguard_manager.py:135-142`
 * - block pages — `hub_api/modules/sase/security/blockpages/api.py:111-126`
 * - SWG policies — `hub_api/modules/sase/security/swg/api.py:237-245`
 *
 * Traps these types encode:
 *
 * - A WireGuard peer has NO `id`. It is identified by `node_id`, and its
 *   `public_key` is the only other stable field, so the table keys on
 *   `node_id`.
 * - A client's `cluster_id` may be null — an enrolled client is not yet
 *   assigned to a cluster — so it is not the row key either.
 * - A block page's `markdown` is the authored source and `status` is a draft
 *   /published lifecycle, not health. They are different questions and both
 *   are shown.
 * - A SWG policy's `scope_id` is null for a tenant-wide policy. Rendering that
 *   as blank would read as a missing value rather than "applies to everyone".
 */

/** An SD-WAN client (Tobogganing calls the collection `clients`). */
export interface TobogganingClient {
  id: string;
  name?: string | null;
  type?: string | null;
  cluster_id?: string | null;
  status?: string | null;
  last_seen?: string | null;
}

/** An SD-WAN cluster. `client_count` is reported by the product, not derived. */
export interface TobogganingCluster {
  id: string;
  name?: string | null;
  region?: string | null;
  datacenter?: string | null;
  status?: string | null;
  client_count?: number | null;
}

/**
 * A WireGuard peer.
 *
 * Three fields, and no `id` among them. `public_key` is a peer's WireGuard
 * identity and is safe to display — it is the PUBLIC half; the private key is
 * never returned by this route and is not modelled here.
 */
export interface TobogganingPeer {
  node_id: string;
  public_key?: string | null;
  ip_address?: string | null;
}

/** A SASE block page. `status` is a draft/published lifecycle. */
export interface TobogganingBlockPage {
  id: string;
  tenant?: string | null;
  name?: string | null;
  markdown?: string | null;
  status?: string | null;
  version?: number | null;
  created_by?: string | null;
  updated_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Rendered preview of a block page, from `POST .../preview`. */
export interface TobogganingBlockPagePreview {
  html: string;
  variables?: Record<string, string> | null;
}

/**
 * One SWG category policy.
 *
 * `scope` is `tenant` | `group` | `user`; `scope_id` is null for the
 * tenant-wide case. `action` is what the policy does to a matching request.
 */
export interface TobogganingSwgPolicy {
  id: string;
  scope?: string | null;
  scope_id?: string | null;
  category?: string | null;
  action?: string | null;
}

/** Row shape the peers table renders — keyed by node_id, which has no `id`. */
export type TobogganingPeerRow = TobogganingPeer & { id: string };

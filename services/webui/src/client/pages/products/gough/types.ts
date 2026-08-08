/**
 * Gough payload shapes as they arrive through the portal proxy.
 *
 * These mirror `services/portal-api/app/adapters/gough/mapping.py`, which was
 * written against Gough's live api-manager handlers rather than its committed
 * openapi-spec.yaml (that spec is stale — it still documents /servers,
 * /servers/{id}/power/{action} and /stats, none of which the service
 * registers). Field names here are the live ones.
 *
 * Two traps the backend mapping documents and these types encode:
 *
 * - A node has no `status`. It has `state` (lifecycle) and `posture`
 *   (compliance), which answer different questions — a node can be `ready`
 *   and non-compliant. Typing a `status` field here would produce a column
 *   that is empty on every row.
 * - `total` on a list response is the length of the page just serialised,
 *   NOT the collection size, so it is deliberately absent below. Rendering it
 *   as a count shows "12 nodes" on every page of a 400-node fleet.
 */

/** A physical machine under Gough's management. */
export interface GoughNode {
  id: string;
  name: string;
  state?: string | null;
  posture?: string | null;
  ipv4?: string | null;
  primary_nic_mac?: string | null;
  firmware_type?: string | null;
  hardware_tags?: string[];
  discovered_at?: string | null;
  deployed_at?: string | null;
}

/** A deployable workload definition. */
export interface GoughBiome {
  id: string;
  name: string;
  is_active?: boolean | null;
  biome_kind?: string | null;
  phase?: string | null;
  version?: string | null;
  workload_type?: string | null;
  is_default?: boolean | null;
  requires_hardware_tags?: string[];
}

/** An enrolled access agent. Addressed by `agent_id`, not the row `id`. */
export interface GoughAgent {
  id: string;
  agent_id?: string;
  hostname?: string | null;
  status?: string | null;
  ip_address?: string | null;
  last_heartbeat?: string | null;
  enrolled_at?: string | null;
  enrollment_completed?: boolean | null;
}

/**
 * A long-running product operation, as published by the portal's own
 * operations endpoints (not the proxy).
 *
 * `state` is the normalised value to branch on; `status` is Gough's verbatim
 * string, for display only. `is_terminal` is published precisely so the UI
 * never has to enumerate terminal states itself — poll while it is false.
 */
export interface GoughOperation {
  id: string;
  kind: string;
  state: string;
  status: string;
  is_terminal: boolean;
  resource_id?: string | null;
  resource_kind?: string | null;
  /**
   * Null unless the product reports enough to compute a real fraction. A
   * Gough upgrade run publishes nodes_completed/nodes_total and yields one;
   * a deployment publishes only an unbounded `phase` integer and yields
   * null. The bar is hidden rather than invented in that case.
   */
  progress?: number | null;
  detail?: string | null;
  error?: string | null;
  /**
   * What a succeeded operation produced — the success counterpart of `error`.
   * Null when the operation produced no artefact.
   */
  result?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
}

/** One line of an operation's log stream. */
export interface GoughOperationLogLine {
  timestamp?: string | null;
  level?: string | null;
  message: string;
}

/** Every Gough resource a screen in this directory lists. */
export type GoughResourceKind = "nodes" | "biomes" | "agents";

/** The affected resource's post-action state, when the product returned it. */
export interface GoughActionResource {
  id: string;
  kind: string;
  name: string;
  status?: string | null;
}

/**
 * Outcome of a product action, from the TYPED portal route.
 *
 * `operations` is why this type exists. A proxied action returns the product's
 * raw body, which carries no poll key — the UI could only invalidate its
 * queries and hope. Through the typed route each started operation comes back
 * already addressable at `/operations/{kind}/{id}`, so the UI can follow
 * exactly the work it started. It is a LIST because one Gough node deploy
 * starts one deployment per assigned biome.
 */
export interface GoughActionResult {
  action: string;
  accepted: boolean;
  operations: GoughOperation[];
  resource?: GoughActionResource | null;
  message?: string | null;
}

/**
 * Row shapes as the tables render them.
 *
 * `DataTable` keys its rows by a string `id`, while Gough numbers node and
 * biome ids and identifies an agent by `agent_id`. The pages normalise that
 * before rendering, so the COLUMN definitions must be typed against the
 * normalised row — not the raw resource.
 *
 * Getting this wrong is what the `as never` casts were hiding. `ColumnConfig<T>`
 * is invariant in `T` (`key: keyof T`, and `render` takes `T[keyof T]`), so
 * `ColumnConfig<GoughNode>[]` genuinely is not assignable where
 * `ColumnConfig<GoughNodeRow>[]` is required. `as never` silenced that by
 * erasing the type instead of correcting it, which also disabled every real
 * check on those column definitions — a typo in a `key` would have compiled.
 */
export type GoughNodeRow = GoughNode & { id: string };
export type GoughBiomeRow = GoughBiome & { id: string };
export type GoughAgentRow = GoughAgent & { id: string };

/**
 * Headline metrics for the connection, from the product's own /metrics scrape.
 *
 * `totals` is the part the dashboard counter tiles read. It is NOT the same as
 * counting rows from a resource list: a list page is capped (Gough's
 * `page_size` maxes at 500) and Gough's own `total` is the length of the page
 * it just serialised, so a fleet larger than one page renders as the page size.
 */
export interface GoughMetricsSummary {
  start: string;
  end: string;
  series: {
    key: string;
    label: string;
    unit: string;
    points: { timestamp: string; value: number }[];
  }[];
  totals: Record<string, number>;
}

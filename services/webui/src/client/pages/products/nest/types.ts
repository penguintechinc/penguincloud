/**
 * Nest payload shapes as they arrive through the portal.
 *
 * Transcribed from `~/code/nest/apps/api/models.py` (`DataResourceRecord`,
 * `VolumeSnapshotRecord`) and `services/cost-calculator/calculator.go`, not
 * from `openapi/v1.yaml` — Session 1 established that spec is incomplete
 * (21 registered routes against 18 documented) and wrong about the create
 * body. Field names here are the live ones.
 *
 * Traps these types encode:
 *
 * - A DataResource has `phase`, not `status`; and separately `healthState`.
 *   They answer different questions — a resource can be `Ready` and unhealthy.
 * - `id` is a UUID but is NOT the addressable identity. Every Nest route takes
 *   `/{name}`, so the screens key on `name`; the UUID is display-only.
 * - `importConnStr` is deliberately absent. It is a database connection string
 *   for an imported resource and can carry credentials, so it is neither typed
 *   nor rendered nor logged here.
 */

/** A Nest DataResource — the portal calls these Databases. */
export interface NestDatabase {
  id: string;
  name: string;
  resourceType?: string | null;
  engineType?: string | null;
  storageClass?: string | null;
  driverType?: string | null;
  origination?: string | null;
  phase?: string | null;
  namespace?: string | null;
  sizeGi?: number | null;
  healthState?: string | null;
  healthMessage?: string | null;
  healthLastCheck?: string | null;
  externalProvider?: string | null;
  externalEndpoint?: string | null;
  externalRegion?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

/** A VolumeSnapshot. `sourcePVC` is the edge back to the database. */
export interface NestSnapshot {
  name: string;
  sourcePVC?: string | null;
  snapshotClass?: string | null;
  readyToUse?: boolean | null;
  creationTime?: string | null;
  sizeBytes?: number | null;
}

/**
 * A long-running Nest operation, from the portal's typed operations route.
 *
 * `state` is the normalised value to branch on; `status` is Nest's verbatim
 * phase, for display. `is_terminal` is published so the UI never enumerates
 * terminal states itself — poll while it is false.
 *
 * `progress` is always null for Nest: it publishes a phase and nothing
 * countable, and the contract forbids synthesising a fraction from a state.
 * `result` is what the operation PRODUCED — the snapshot taken, the restore
 * target, the migration report. It is the reason the contract has the field.
 */
export interface NestOperation {
  id: string;
  kind: string;
  state: string;
  status: string;
  is_terminal: boolean;
  resource_id?: string | null;
  resource_kind?: string | null;
  progress?: number | null;
  detail?: string | null;
  error?: string | null;
  result?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
}

/** Outcome of a Nest action, from the typed portal route. */
export interface NestActionResult {
  action: string;
  accepted: boolean;
  operations: NestOperation[];
  message?: string | null;
}

/**
 * A created resource, from the typed portal create route.
 *
 * `operation_id` is null when the create finished synchronously; Nest answers
 * 202 for every create, so in practice it is present and is what lets the
 * screen watch provisioning rather than reporting the row as ready the moment
 * creation was accepted.
 */
export interface NestCreatedResource {
  id: string;
  kind: string;
  name: string;
  status?: string | null;
  operation_id?: string | null;
}

/** One month of metered usage, from the cost-calculator service. */
export interface NestUsageRecord {
  tenantId?: string | null;
  month: string;
  totalTokens?: number | null;
  totalCostUsd?: number | null;
  breakdown?: Record<string, number> | null;
  updatedAt?: string | null;
}

/** Aggregate across every month the calculator holds. */
export interface NestCostSummary {
  totalTokens?: number | null;
  totalCostUsd?: number | null;
  months?: number | null;
}

/**
 * A billing read that may legitimately have no data to show.
 *
 * Nest's cost routes proxy to `nest-cost-calculator`, and answer 503 when that
 * service is absent — a normal deployment state, not a fault of this tenant.
 * Modelling it explicitly is what keeps the screen from rendering "unavailable"
 * as an empty table, which reads as "you were billed nothing".
 */
export interface NestBillingResult<T> {
  available: boolean;
  data: T | null;
}

/** Row shape the databases table renders — keyed by name, not by UUID. */
export type NestDatabaseRow = NestDatabase & { id: string };

/** Row shape the usage table renders — keyed by month. */
export type NestUsageRow = NestUsageRecord & { id: string };

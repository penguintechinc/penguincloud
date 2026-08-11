/**
 * Query key factory for TanStack Query
 * Provides type-safe, hierarchical query keys for all data-fetching operations
 *
 * Anything fetched per-tenant carries the tenant id IN the key. Without it, a
 * tenant switch reuses the previous tenant's cached rows under an identical
 * key — a cross-tenant data leak in the UI, not just a staleness bug.
 */

import type { ApiPath } from "./portal";

export const queryKeys = {
  all: () => ["api"] as const,

  // Dashboard
  // Tenant-scoped keys accept `undefined` (no tenant selected yet) rather than
  // forcing callers to invent a sentinel id at the call site.
  dashboard: () => [...queryKeys.all(), "dashboard"] as const,
  dashboardOverview: (tenantId: number | undefined) =>
    [...queryKeys.dashboard(), "overview", tenantId] as const,
  dashboardActivity: (tenantId: number | undefined, limit: number) =>
    [...queryKeys.dashboard(), "activity", tenantId, limit] as const,
  dashboardRollup: (tenantId: number | undefined) =>
    [...queryKeys.dashboard(), "rollup", tenantId] as const,

  // Feature flags + licence tier + dev-mode signal.
  //
  // NOT tenant-scoped, unlike almost everything else here: flags are
  // evaluated per USER (the PostHog distinct_id) and the licence is a
  // property of the deployment, so neither changes when the active tenant
  // does. Keying it by tenant would refetch on every switch and, worse,
  // imply a per-tenant answer the server does not give.
  features: () => [...queryKeys.all(), "features"] as const,

  // Health checks
  health: () => [...queryKeys.all(), "health"] as const,
  healthOverview: (tenantId: number | undefined) =>
    [...queryKeys.health(), "overview", tenantId] as const,

  // Tenants
  tenants: () => [...queryKeys.all(), "tenants"] as const,
  tenantList: (includeChildren: boolean) =>
    [...queryKeys.tenants(), "list", includeChildren] as const,
  tenant: (id: string) => [...queryKeys.tenants(), id] as const,
  tenantMembers: (tenantId: number | undefined) =>
    [...queryKeys.tenants(), "members", tenantId] as const,
  tenantUsage: (tenantId: number | undefined) =>
    [...queryKeys.tenants(), "usage", tenantId] as const,

  // Connections (product connections registered to a tenant)
  connections: () => [...queryKeys.all(), "connections"] as const,
  connectionsByTenant: (tenantId: number | undefined) =>
    [...queryKeys.connections(), "tenant", tenantId] as const,
  connection: (id: string) => [...queryKeys.connections(), id] as const,

  // Product type catalogue (global, not tenant-scoped)
  productTypes: () => [...queryKeys.all(), "product-types"] as const,

  // Gough resources, reached through the proxy.
  //
  // Keyed by tenant AND connection id. The connection id alone would look
  // sufficient — a connection belongs to exactly one tenant — but the tenant
  // id is what every other key in this file carries, and dropping it here
  // would make Gough the one surface where a tenant switch does not
  // partition the cache. Same rule, no exception.
  gough: () => [...queryKeys.all(), "gough"] as const,
  goughResource: (
    tenantId: number | undefined,
    productId: number | undefined,
    kind: string,
  ) => [...queryKeys.gough(), tenantId, productId, kind] as const,
  goughOperations: (
    tenantId: number | undefined,
    productId: number | undefined,
  ) => [...queryKeys.gough(), tenantId, productId, "operations"] as const,
  goughMetrics: (tenantId: number | undefined, productId: number | undefined) =>
    [...queryKeys.gough(), tenantId, productId, "metrics"] as const,
  goughOperationLogs: (
    tenantId: number | undefined,
    productId: number | undefined,
    kind: string,
    operationId: string,
  ) =>
    [
      ...queryKeys.gough(),
      tenantId,
      productId,
      "operation-logs",
      kind,
      operationId,
    ] as const,

  // Nest resources, reached through the proxy (reads) and the typed portal
  // routes (writes, operation polling).
  //
  // Tenant-scoped for the same reason every other key here is: without the
  // tenant id a tenant switch reuses the previous tenant's rows under an
  // identical key, which is a cross-tenant leak in the UI rather than
  // staleness. Nest makes that sharper than most — a Nest connection is
  // addressed by a tenant-substituted path, so two tenants' rows genuinely
  // come from different upstream URLs under an otherwise identical key.
  nest: () => [...queryKeys.all(), "nest"] as const,
  nestResource: (
    tenantId: number | undefined,
    productId: number | undefined,
    kind: string,
  ) => [...queryKeys.nest(), tenantId, productId, kind] as const,
  nestOperation: (
    tenantId: number | undefined,
    productId: number | undefined,
    operationId: string,
  ) =>
    [
      ...queryKeys.nest(),
      tenantId,
      productId,
      "operation",
      operationId,
    ] as const,

  // Tobogganing resources, all reached through the proxy.
  //
  // Tenant-scoped like every other product key. Tobogganing makes the reason
  // unusually direct: it takes no tenant in any path and scopes every read
  // from the `tenant` claim in the credential the portal presents, so two
  // tenants' rows arrive from an IDENTICAL upstream URL. Without the tenant id
  // in the key, a tenant switch would serve the previous tenant's clients and
  // peers from cache under a key that is correct in every other respect — a
  // cross-tenant leak in the UI with nothing in the URL to reveal it.
  tobogganing: () => [...queryKeys.all(), "tobogganing"] as const,
  tobogganingResource: (
    tenantId: number | undefined,
    productId: number | undefined,
    kind: string,
  ) => [...queryKeys.tobogganing(), tenantId, productId, kind] as const,

  // Users
  users: () => [...queryKeys.all(), "users"] as const,
  userList: (page: number, perPage: number) =>
    [...queryKeys.users(), "list", page, perPage] as const,
  user: (id: string) => [...queryKeys.users(), id] as const,

  // Audit logs
  auditLogs: () => [...queryKeys.all(), "audit"] as const,
  auditLogPage: (tenantId: number | undefined, page: number, perPage: number) =>
    [...queryKeys.auditLogs(), tenantId, page, perPage] as const,

  // Teams (tenant-scoped)
  teams: () => [...queryKeys.all(), "teams"] as const,
  teamList: (tenantId: number | undefined) =>
    [...queryKeys.teams(), "list", tenantId] as const,

  /**
   * Key for a call made through the generated typed client (`portal.ts`).
   *
   * `path` is constrained to `ApiPath`, so a key can only be built for an
   * endpoint the OpenAPI document actually describes — a renamed or removed
   * route becomes a compile error here rather than a cache entry that is
   * never invalidated because nothing writes to it any more.
   *
   * The tenant id stays in the key for the same reason every other
   * tenant-scoped key above carries it: without it, a tenant switch reuses
   * the previous tenant's cached rows under an identical key, which is a
   * cross-tenant data leak in the UI rather than a staleness bug.
   */
  endpoint: (
    path: ApiPath,
    tenantId: number | undefined,
    params?: Readonly<Record<string, unknown>>,
  ) =>
    [...queryKeys.all(), "endpoint", path, tenantId, params ?? null] as const,
};

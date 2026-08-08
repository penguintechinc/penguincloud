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
  goughOperation: (
    tenantId: number | undefined,
    productId: number | undefined,
    kind: string,
    operationId: string,
  ) =>
    [
      ...queryKeys.gough(),
      tenantId,
      productId,
      "operation",
      kind,
      operationId,
    ] as const,

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

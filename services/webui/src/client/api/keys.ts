/**
 * Query key factory for TanStack Query
 * Provides type-safe, hierarchical query keys for all data-fetching operations
 */

export const queryKeys = {
  all: () => ["api"] as const,

  // Dashboard
  dashboard: () => [...queryKeys.all(), "dashboard"] as const,

  // Health checks
  health: () => [...queryKeys.all(), "health"] as const,

  // Tenants
  tenants: () => [...queryKeys.all(), "tenants"] as const,
  tenant: (id: string) => [...queryKeys.tenants(), id] as const,

  // Connections
  connections: () => [...queryKeys.all(), "connections"] as const,
  connection: (id: string) => [...queryKeys.connections(), id] as const,

  // Users
  users: () => [...queryKeys.all(), "users"] as const,
  user: (id: string) => [...queryKeys.users(), id] as const,

  // Audit logs
  auditLogs: () => [...queryKeys.all(), "audit"] as const,
};

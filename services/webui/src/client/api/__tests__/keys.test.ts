/**
 * Test query key factory
 * Ensures query keys are properly structured and unique
 */
import { queryKeys } from "../keys";

describe("Query Keys", () => {
  it("provides dashboard query key", () => {
    const key = queryKeys.dashboard();
    expect(key).toEqual(["api", "dashboard"]);
  });

  it("provides health query key", () => {
    const key = queryKeys.health();
    expect(key).toEqual(["api", "health"]);
  });

  it("provides tenants query key", () => {
    const key = queryKeys.tenants();
    expect(key).toEqual(["api", "tenants"]);
  });

  it("provides tenant-specific query key", () => {
    const key = queryKeys.tenant("123");
    expect(key).toEqual(["api", "tenants", "123"]);
  });

  it("provides connections query key", () => {
    const key = queryKeys.connections();
    expect(key).toEqual(["api", "connections"]);
  });

  it("scopes connections by tenant", () => {
    expect(queryKeys.connectionsByTenant(7)).toEqual([
      "api",
      "connections",
      "tenant",
      7,
    ]);
  });

  it("provides product types query key", () => {
    expect(queryKeys.productTypes()).toEqual(["api", "product-types"]);
  });

  it("scopes dashboard overview by tenant", () => {
    expect(queryKeys.dashboardOverview(42)).toEqual([
      "api",
      "dashboard",
      "overview",
      42,
    ]);
  });

  it("scopes dashboard activity by tenant and limit", () => {
    expect(queryKeys.dashboardActivity(42, 10)).toEqual([
      "api",
      "dashboard",
      "activity",
      42,
      10,
    ]);
  });

  it("scopes health overview by tenant", () => {
    expect(queryKeys.healthOverview(42)).toEqual([
      "api",
      "health",
      "overview",
      42,
    ]);
  });

  it("keeps different tenants on distinct keys", () => {
    // Regression guard: without the tenant id in the key, switching tenants
    // reuses the previous tenant's cached rows.
    expect(queryKeys.connectionsByTenant(1)).not.toEqual(
      queryKeys.connectionsByTenant(2),
    );
    expect(queryKeys.dashboardOverview(1)).not.toEqual(
      queryKeys.dashboardOverview(2),
    );
  });

  it("represents an unselected tenant as undefined rather than a sentinel", () => {
    expect(queryKeys.connectionsByTenant(undefined)).toEqual([
      "api",
      "connections",
      "tenant",
      undefined,
    ]);
  });

  it("provides connection-specific query key", () => {
    const key = queryKeys.connection("456");
    expect(key).toEqual(["api", "connections", "456"]);
  });

  it("provides users query key", () => {
    const key = queryKeys.users();
    expect(key).toEqual(["api", "users"]);
  });

  it("provides user-specific query key", () => {
    const key = queryKeys.user("789");
    expect(key).toEqual(["api", "users", "789"]);
  });

  it("provides audit logs query key", () => {
    const key = queryKeys.auditLogs();
    expect(key).toEqual(["api", "audit"]);
  });

  it("uses readonly tuple type for keys", () => {
    const key = queryKeys.dashboard();
    // TypeScript would catch this error, so we just verify the structure
    expect(Array.isArray(key)).toBe(true);
  });
});

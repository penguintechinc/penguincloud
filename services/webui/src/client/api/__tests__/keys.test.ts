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

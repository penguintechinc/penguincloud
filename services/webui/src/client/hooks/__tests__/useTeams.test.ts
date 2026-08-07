/**
 * Tests for useTeams hook.
 *
 * Ensures query keys are properly tenant-scoped to prevent cross-tenant
 * cache collisions when switching tenants.
 */

import { queryKeys } from "../../api/keys";

describe("useTeams query keys", () => {
  it("generates distinct keys for different tenants", () => {
    const key1 = queryKeys.teamList(1);
    const key2 = queryKeys.teamList(2);
    const keyUndef = queryKeys.teamList(undefined);

    expect(key1).not.toEqual(key2);
    expect(key1).not.toEqual(keyUndef);
    expect(key2).not.toEqual(keyUndef);
  });

  it("includes tenant id in the key to prevent cross-tenant cache leak", () => {
    const key = queryKeys.teamList(42);

    // Key should be a tuple with the tenant id embedded
    expect(key).toContain(42);
    expect(key).toContain("list");
    expect(key).toContain("teams");
  });

  it("returns consistent keys for the same tenant", () => {
    const key1 = queryKeys.teamList(1);
    const key2 = queryKeys.teamList(1);

    expect(key1).toEqual(key2);
  });

  it("returns different keys for undefined vs defined tenant", () => {
    const keyDefined = queryKeys.teamList(1);
    const keyUndefined = queryKeys.teamList(undefined);

    expect(keyDefined).not.toEqual(keyUndefined);
  });
});

/**
 * Tests for the tenant grouping/search helpers behind the scope switcher.
 */

import { groupTenants, filterGroups } from "../tenantGrouping";
import type { Tenant } from "../../../types";

const tenants = [
  { id: 1, name: "Provider A", display_name: "Acme", parent_tenant_id: null },
  { id: 2, name: "Customer One", display_name: "", parent_tenant_id: 1 },
  { id: 3, name: "Customer Two", display_name: "Two", parent_tenant_id: 1 },
  { id: 4, name: "Provider B", display_name: "Beta", parent_tenant_id: null },
] as unknown as Tenant[];

describe("groupTenants", () => {
  it("nests customers under their provider", () => {
    const groups = groupTenants(tenants);

    expect(groups.map((g) => g.tenantId)).toEqual([1, 4]);
    expect(groups[0].children.map((c) => c.tenantId)).toEqual([2, 3]);
  });

  it("prefers display_name and falls back to name", () => {
    const groups = groupTenants(tenants);

    expect(groups[0].name).toBe("Acme");
    expect(groups[0].children[0].name).toBe("Customer One");
    expect(groups[0].children[1].name).toBe("Two");
  });

  it("leaves a provider with no customers empty", () => {
    expect(groupTenants(tenants)[1].children).toEqual([]);
  });

  it("returns nothing for an empty roster", () => {
    expect(groupTenants([])).toEqual([]);
  });
});

describe("filterGroups", () => {
  const groups = groupTenants(tenants);

  it("returns everything for an empty query", () => {
    expect(filterGroups(groups, "")).toHaveLength(2);
  });

  it("keeps a provider that matches even when no customer does", () => {
    const result = filterGroups(groups, "acme");

    expect(result).toHaveLength(1);
    expect(result[0].children).toEqual([]);
  });

  it("keeps a provider whose customer matches", () => {
    const result = filterGroups(groups, "two");

    expect(result).toHaveLength(1);
    expect(result[0].children.map((c) => c.tenantId)).toEqual([3]);
  });

  it("is case-insensitive", () => {
    expect(filterGroups(groups, "TWO")[0].children).toHaveLength(1);
  });

  it("drops groups that match nothing", () => {
    expect(filterGroups(groups, "nothing-here")).toEqual([]);
  });
});

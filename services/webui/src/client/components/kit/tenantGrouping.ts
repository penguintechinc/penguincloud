/**
 * Grouping and search helpers for the tenant scope switcher.
 * Pure functions, split out of TenantScopeSwitcher.tsx to keep it focused on
 * rendering and to make the hierarchy rules testable on their own.
 */

import type { Tenant } from "../../types";

export interface TenantOption {
  tenantId: number;
  name: string;
}

export interface TenantGroup extends TenantOption {
  children: TenantOption[];
}

function label(tenant: Tenant): string {
  return tenant.display_name || tenant.name;
}

/**
 * Buckets a flat tenant list into provider → customer groups. A tenant with no
 * `parent_tenant_id` is a provider; everything else hangs off its parent.
 */
export function groupTenants(tenants: Tenant[]): TenantGroup[] {
  return tenants
    .filter((t) => !t.parent_tenant_id)
    .map((provider) => ({
      tenantId: provider.id,
      name: label(provider),
      children: tenants
        .filter((t) => t.parent_tenant_id === provider.id)
        .map((customer) => ({
          tenantId: customer.id,
          name: label(customer),
        })),
    }));
}

/**
 * Filters groups by a case-insensitive substring. A provider survives if it
 * matches directly or if any of its customers do.
 */
export function filterGroups(
  groups: TenantGroup[],
  query: string,
): TenantGroup[] {
  const needle = query.toLowerCase();
  return groups
    .map((group) => ({
      ...group,
      children: group.children.filter((child) =>
        child.name.toLowerCase().includes(needle),
      ),
    }))
    .filter(
      (group) =>
        group.name.toLowerCase().includes(needle) || group.children.length > 0,
    );
}

/**
 * Tenant endpoints, including hierarchy listing and scope switching.
 * `include_children` requires delegated admin on the server side.
 */

import api from "../../lib/api";
import { portalUrl } from "../portalPaths";
import type { Tenant, TenantMember, TenantUsage } from "../../types";

export const tenantsApi = {
  list: async (
    includeChildren = false,
  ): Promise<{ tenants: Tenant[]; count?: number }> => {
    const response = await api.get(portalUrl.tenants(), {
      params: includeChildren ? { include_children: true } : undefined,
    });
    return response.data;
  },
  get: async (id: number): Promise<Tenant> => {
    const response = await api.get(portalUrl.tenant(id));
    return response.data;
  },
  create: async (data: {
    name: string;
    slug: string;
    display_name?: string;
    plan?: string;
  }): Promise<Tenant> => {
    const response = await api.post(portalUrl.tenants(), data);
    return response.data;
  },
  update: async (id: number, data: Partial<Tenant>): Promise<Tenant> => {
    const response = await api.put(portalUrl.tenant(id), data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(portalUrl.tenant(id));
  },
  switchTenant: async (
    id: number,
  ): Promise<{
    access_token: string;
    refresh_token?: string;
    tenant: Tenant;
    tenant_role: string;
  }> => {
    const response = await api.post(portalUrl.tenantSwitch(id));
    return response.data;
  },
  getMembers: async (
    id: number,
  ): Promise<{ members: TenantMember[]; count: number }> => {
    const response = await api.get(portalUrl.tenantMembers(id));
    return response.data;
  },
  addMember: async (
    id: number,
    userId: number,
    role: string,
  ): Promise<TenantMember> => {
    const response = await api.post(portalUrl.tenantMembers(id), {
      user_id: userId,
      role,
    });
    return response.data;
  },
  updateMember: async (
    tenantId: number,
    userId: number,
    role: string,
  ): Promise<TenantMember> => {
    const response = await api.put(portalUrl.tenantMember(tenantId, userId), {
      role,
    });
    return response.data;
  },
  removeMember: async (tenantId: number, userId: number): Promise<void> => {
    await api.delete(portalUrl.tenantMember(tenantId, userId));
  },
  getUsage: async (id: number): Promise<TenantUsage> => {
    const response = await api.get(portalUrl.tenantUsage(id));
    return response.data;
  },
};

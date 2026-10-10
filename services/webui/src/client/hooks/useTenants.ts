/**
 * TanStack Query hooks for tenant server state.
 *
 * These replace the `tenants` / `members` / `usage` slices that used to live in
 * tenantStore. Zustand now holds only the active scope (`currentTenant`),
 * which is client state; everything fetched from the API is owned by TanStack
 * Query so caching and invalidation have one implementation.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tenantsApi } from "../api/resources/tenants";
import { queryKeys } from "../api/keys";
import type { Tenant, TenantMember, TenantUsage } from "../types";

/**
 * Tenants visible to the caller. `includeChildren` asks the server for the
 * provider subtree and requires delegated admin.
 */
export function useTenants(includeChildren = false) {
  return useQuery({
    queryKey: queryKeys.tenantList(includeChildren),
    queryFn: async (): Promise<Tenant[]> => {
      const response = await tenantsApi.list(includeChildren);
      return response.tenants ?? [];
    },
  });
}

/** Members of one tenant. Disabled until a tenant is selected. */
export function useTenantMembers(tenantId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.tenantMembers(tenantId),
    queryFn: async (): Promise<TenantMember[]> => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      const response = await tenantsApi.getMembers(tenantId);
      return response.members ?? [];
    },
    enabled: tenantId !== undefined,
  });
}

/** Usage/quota counters for one tenant. */
export function useTenantUsage(tenantId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.tenantUsage(tenantId),
    queryFn: async (): Promise<TenantUsage> => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      return tenantsApi.getUsage(tenantId);
    },
    enabled: tenantId !== undefined,
  });
}

export function useCreateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      slug: string;
      display_name?: string;
      plan?: string;
    }) => tenantsApi.create(data),
    onSuccess: () => {
      console.log("[useCreateTenant] Created { invalidating: true }");
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants() });
    },
  });
}

export function useUpdateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Tenant> }) =>
      tenantsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants() });
    },
  });
}

export function useDeleteTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => tenantsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants() });
    },
  });
}

export function useAddTenantMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      tenantId,
      userId,
      role,
    }: {
      tenantId: number;
      userId: number;
      role: string;
    }) => tenantsApi.addMember(tenantId, userId, role),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.tenantMembers(variables.tenantId),
      });
    },
  });
}

export function useRemoveTenantMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tenantId, userId }: { tenantId: number; userId: number }) =>
      tenantsApi.removeMember(tenantId, userId),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.tenantMembers(variables.tenantId),
      });
    },
  });
}

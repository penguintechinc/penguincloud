/**
 * TanStack Query hook for fetching teams.
 *
 * The query key includes tenantId to ensure tenant switches invalidate the cache
 * and refetch team data for the new tenant. Without tenantId in the key, switching
 * tenants would reuse the previous tenant's cached list — a cross-tenant leak.
 */

import { useQuery } from "@tanstack/react-query";
import api from "../lib/api";
import { queryKeys } from "../api/keys";

export interface Team {
  id?: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

/**
 * Fetches teams for the current tenant. tenantId should come from currentTenant.id.
 * Stays disabled (no fetch) until tenantId is defined.
 */
export function useTeams(tenantId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.teamList(tenantId),
    queryFn: async () => {
      // Guarded by `enabled` below; the assertion keeps queryFn total.
      if (tenantId === undefined) return [];
      const response = await api.get<{ teams: Team[] }>("/teams");
      return response.data.teams;
    },
    staleTime: 5 * 60 * 1000,
    enabled: tenantId !== undefined,
  });
}

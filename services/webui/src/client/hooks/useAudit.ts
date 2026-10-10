/**
 * TanStack Query hook for audit log pages.
 *
 * The key carries the tenant id: without it a tenant switch would serve the
 * previous tenant's log rows from cache under an identical key.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { auditApi } from "../api/resources/dashboard";
import { queryKeys } from "../api/keys";
import type { AuditLog } from "../types";

export interface AuditLogPage {
  logs: AuditLog[];
  total: number;
}

export function useAuditLogs(
  tenantId: number | undefined,
  page: number,
  perPage: number,
) {
  return useQuery({
    queryKey: queryKeys.auditLogPage(tenantId, page, perPage),
    queryFn: async (): Promise<AuditLogPage> => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      const response = await auditApi.logs(tenantId, page, perPage);
      return { logs: response.logs ?? [], total: response.total ?? 0 };
    },
    enabled: tenantId !== undefined,
    // Paging keeps the previous page on screen instead of flashing the
    // skeleton on every Next click.
    placeholderData: keepPreviousData,
  });
}

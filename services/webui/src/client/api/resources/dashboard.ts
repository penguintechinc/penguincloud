/**
 * Dashboard aggregation endpoints, for both single-tenant and provider scope.
 */

import api from "../../lib/api";
import type {
  AuditLog,
  DashboardOverview,
  DashboardRollupRow,
} from "../../types";

export const dashboardApi = {
  overview: async (tenantId: number): Promise<DashboardOverview> => {
    const response = await api.get("/dashboard/overview", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  health: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get("/dashboard/health", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  activity: async (
    tenantId: number,
    limit = 20,
  ): Promise<{ activity: AuditLog[]; count: number }> => {
    const response = await api.get("/dashboard/activity", {
      params: { tenant_id: tenantId, limit },
    });
    return response.data;
  },
  alerts: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get("/dashboard/alerts", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  /**
   * Per-customer × per-product status for a provider org. Only meaningful in
   * provider scope; the server requires delegated admin over the subtree.
   */
  rollup: async (tenantId: number): Promise<DashboardRollupRow[]> => {
    const response = await api.get("/dashboard/rollup", {
      params: { tenant_id: tenantId },
    });
    return response.data.rollup ?? [];
  },
};

export const auditApi = {
  logs: async (
    tenantId: number,
    page = 1,
    perPage = 50,
  ): Promise<{ logs: AuditLog[]; total: number }> => {
    const response = await api.get("/audit/logs", {
      params: { tenant_id: tenantId, page, per_page: perPage },
    });
    return response.data;
  },
  export: async (
    tenantId: number,
    format: "json" | "csv" = "json",
    limit = 1000,
  ): Promise<Blob | Record<string, unknown>> => {
    const response = await api.get("/audit/export", {
      params: { tenant_id: tenantId, format, limit },
      responseType: format === "csv" ? "blob" : "json",
    });
    return response.data;
  },
};

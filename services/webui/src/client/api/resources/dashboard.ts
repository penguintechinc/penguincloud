/**
 * Dashboard aggregation endpoints, for both single-tenant and provider scope.
 */

import api from "../../lib/api";
import { envelopeList } from "../envelope";
import { portalUrl } from "../portalPaths";
import type {
  AuditLog,
  DashboardOverview,
  DashboardRollupRow,
} from "../../types";

export const dashboardApi = {
  overview: async (tenantId: number): Promise<DashboardOverview> => {
    const response = await api.get(portalUrl.dashboardOverview(), {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  health: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get(portalUrl.dashboardHealth(), {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  activity: async (
    tenantId: number,
    limit = 20,
  ): Promise<{ activity: AuditLog[]; count: number }> => {
    const response = await api.get(portalUrl.dashboardActivity(), {
      params: { tenant_id: tenantId, limit },
    });
    return response.data;
  },
  alerts: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get(portalUrl.dashboardAlerts(), {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  /**
   * Per-customer × per-product status for a provider org. Only meaningful in
   * provider scope; the server requires delegated admin over the subtree.
   *
   * The URL is TENANT-SCOPED. It was `GET /dashboard/rollup` with the tenant
   * as a query parameter, and the portal registers no such route — the rule is
   * `/api/v1/tenants/{tenant_id}/dashboard/rollup` (`tenants.py:901`), so
   * every call 404'd. It surfaced as the matrix's error state rather than
   * silently, because `Dashboard.tsx` passes the query error through, but it
   * had never worked. Found by the url_map guard being widened to cover
   * quoted literals.
   *
   * `rollup` is a required field of `RollupResponse`, so an empty subtree
   * arrives as `{"rollup": []}` and a missing key cannot mean "no customers".
   */
  rollup: async (tenantId: number): Promise<DashboardRollupRow[]> => {
    const response = await api.get(portalUrl.tenantDashboardRollup(tenantId));
    return envelopeList<DashboardRollupRow>(response.data, "rollup");
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

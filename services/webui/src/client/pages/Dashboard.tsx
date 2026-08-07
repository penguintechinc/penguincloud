import { useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../hooks/useAuth";
import { useTenantStore } from "../stores/tenantStore";
import { dashboardApi } from "../hooks/useApi";
import { queryKeys } from "../api/keys";
import Card from "../components/Card";
import TabNavigation from "../components/TabNavigation";
import HealthGrid from "../components/HealthGrid";
import type { AuditLog, DashboardOverview, ProductConnection } from "../types";

export default function Dashboard() {
  const { user } = useAuth();
  const { currentTenant } = useTenantStore();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "health", label: "Health Grid" },
    { id: "activity", label: "Recent Activity" },
  ];

  // Fetch dashboard overview
  const overviewQuery = useQuery({
    queryKey: queryKeys.dashboard(),
    queryFn: () => dashboardApi.overview(currentTenant?.id || ""),
    enabled: !!currentTenant,
  });

  // Fetch activity
  const activityQuery = useQuery({
    queryKey: queryKeys.auditLogs(),
    queryFn: () => dashboardApi.activity(currentTenant?.id || "", 10),
    enabled: !!currentTenant,
  });

  // Fetch connections (health grid data)
  const connectionsQuery = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: async () => {
      const response = await dashboardApi.connections(currentTenant?.id || "");
      return response as ProductConnection[];
    },
    enabled: !!currentTenant,
  });

  const isLoading = overviewQuery.isLoading || activityQuery.isLoading;
  const overview = overviewQuery.data;
  const activity = activityQuery.data?.activity || [];
  const connections = connectionsQuery.data || [];

  const handleProductClick = (product: ProductConnection) => {
    navigate(`/products/${product.id}`);
  };

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl text-amber-400 mb-2">Welcome to PenguinCloud</h2>
        <p className="text-slate-400 mb-4">
          Create or select a tenant to get started.
        </p>
        <button
          onClick={() => navigate("/tenants/new")}
          className="btn btn-primary"
        >
          Create Tenant
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">Dashboard</h1>
        <p className="text-slate-400 mt-1">
          {currentTenant.display_name || currentTenant.name} — Welcome back,{" "}
          {user?.full_name || "User"}
        </p>
      </div>

      <TabNavigation
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div className="mt-6">
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card title="Products">
                <div className="text-3xl font-bold text-amber-400">
                  {overview?.stats.total_products || 0}
                </div>
                <div className="text-sm text-slate-400">Connected</div>
              </Card>
              <Card title="Members">
                <div className="text-3xl font-bold text-amber-400">
                  {overview?.stats.total_members || 0}
                </div>
                <div className="text-sm text-slate-400">Team members</div>
              </Card>
              <Card title="Healthy">
                <div className="text-3xl font-bold text-green-400">
                  {overview?.stats.health.healthy || 0}
                </div>
                <div className="text-sm text-slate-400">Products healthy</div>
              </Card>
              <Card title="Alerts">
                <div className="text-3xl font-bold text-red-400">
                  {(overview?.stats.health.unhealthy || 0) +
                    (overview?.stats.health.degraded || 0)}
                </div>
                <div className="text-sm text-slate-400">Need attention</div>
              </Card>
            </div>

            {/* Category breakdown */}
            {overview?.stats.categories &&
              Object.keys(overview.stats.categories).length > 0 && (
                <Card title="Products by Category">
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(overview.stats.categories).map(
                      ([cat, count]) => (
                        <div
                          key={cat}
                          className="px-3 py-1 bg-slate-800 rounded-full text-sm"
                        >
                          <span className="text-slate-400">{cat}:</span>{" "}
                          <span className="text-amber-400">{count}</span>
                        </div>
                      ),
                    )}
                  </div>
                </Card>
              )}
          </div>
        )}

        {activeTab === "health" && (
          <HealthGrid
            products={connections}
            onProductClick={handleProductClick}
          />
        )}

        {activeTab === "activity" && (
          <Card title="Recent Activity">
            {isLoading ? (
              <div className="animate-pulse space-y-2">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-8 bg-slate-700 rounded" />
                ))}
              </div>
            ) : activity.length > 0 ? (
              <div className="space-y-2">
                {activity.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0"
                  >
                    <div>
                      <span className="badge badge-viewer text-xs">
                        {log.action}
                      </span>
                      <span className="text-sm text-slate-300 ml-2">
                        {log.resource_type}
                        {log.resource_id ? ` #${log.resource_id}` : ""}
                      </span>
                    </div>
                    <span className="text-xs text-slate-500">
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400">No recent activity</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

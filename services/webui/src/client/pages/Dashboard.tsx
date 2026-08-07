/**
 * Tenant dashboard. In provider scope it gains a customers × products rollup
 * tab; tab bodies live in ./dashboard/.
 */

import { useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../hooks/useAuth";
import { useTenantStore } from "../stores/tenantStore";
import { dashboardApi } from "../api/resources/dashboard";
import { useProductConnections } from "../hooks/useProducts";
import { queryKeys } from "../api/keys";
import HealthGrid from "../components/HealthGrid";
import TabNavigation from "../components/TabNavigation";
import OverviewTab from "./dashboard/OverviewTab";
import ActivityTab from "./dashboard/ActivityTab";
import RollupMatrix from "./dashboard/RollupMatrix";
import type { ProductConnection } from "../types";

const ACTIVITY_LIMIT = 10;

export default function Dashboard() {
  const { user } = useAuth();
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");

  // `tenantId` is number | undefined — never coerced to a placeholder. Each
  // query stays disabled until a tenant is selected.
  const tenantId = currentTenant?.id;
  const isProviderScope = currentTenant?.kind === "provider";

  const overviewQuery = useQuery({
    queryKey: queryKeys.dashboardOverview(tenantId),
    queryFn: async () => {
      // Runtime guard, not a cast: `enabled` already prevents this, and if that
      // ever regresses we want a loud failure rather than a request carrying a
      // placeholder tenant id.
      if (tenantId === undefined) throw new Error("No tenant selected");
      return dashboardApi.overview(tenantId);
    },
    enabled: tenantId !== undefined,
  });

  const activityQuery = useQuery({
    queryKey: queryKeys.dashboardActivity(tenantId, ACTIVITY_LIMIT),
    queryFn: async () => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      return dashboardApi.activity(tenantId, ACTIVITY_LIMIT);
    },
    enabled: tenantId !== undefined,
  });

  // Only a provider org has customers to roll up; for a customer tenant the
  // endpoint would 403 on the delegated-admin check.
  const rollupQuery = useQuery({
    queryKey: queryKeys.dashboardRollup(tenantId),
    queryFn: async () => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      return dashboardApi.rollup(tenantId);
    },
    enabled: tenantId !== undefined && isProviderScope,
  });

  const connectionsQuery = useProductConnections(tenantId);

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

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "health", label: "Health Grid" },
    ...(isProviderScope ? [{ id: "customers", label: "Customers" }] : []),
    { id: "activity", label: "Recent Activity" },
  ];

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
          <OverviewTab overview={overviewQuery.data} />
        )}

        {activeTab === "health" && (
          <HealthGrid
            products={connectionsQuery.data ?? []}
            onProductClick={handleProductClick}
          />
        )}

        {activeTab === "customers" && isProviderScope && (
          <RollupMatrix
            rows={rollupQuery.data ?? []}
            isLoading={rollupQuery.isLoading}
            error={rollupQuery.error as Error | null}
            onRetry={() => rollupQuery.refetch()}
          />
        )}

        {activeTab === "activity" && (
          <ActivityTab
            activity={activityQuery.data?.activity ?? []}
            isLoading={activityQuery.isLoading}
          />
        )}
      </div>
    </div>
  );
}

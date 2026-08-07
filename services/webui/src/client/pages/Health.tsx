import { useQuery } from "@tanstack/react-query";
import { useTenantStore } from "../stores/tenantStore";
import { useProductConnections } from "../hooks/useProducts";
import { dashboardApi } from "../hooks/useApi";
import { queryKeys } from "../api/keys";
import Card from "../components/Card";
import HealthGrid from "../components/HealthGrid";
import { useNavigate } from "react-router";
import type { ProductConnection } from "../types";

export default function Health() {
  const { currentTenant } = useTenantStore();
  const tenantId = currentTenant?.id;
  const navigate = useNavigate();

  // The aggregate health payload is fetched but not yet rendered — the summary
  // tiles below are derived from the per-connection health_status. Kept as a
  // query (rather than discarded state) so it warms the cache for the health
  // detail work and stays in one place when that lands.
  useQuery({
    queryKey: queryKeys.healthOverview(tenantId),
    queryFn: async () => {
      if (tenantId === undefined) throw new Error("No tenant selected");
      return dashboardApi.health(tenantId);
    },
    enabled: tenantId !== undefined,
  });

  const connectionsQuery = useProductConnections(tenantId);
  const connections = connectionsQuery.data ?? [];
  const isLoading = connectionsQuery.isLoading;

  const handleProductClick = (product: ProductConnection) => {
    navigate(`/products/${product.id}`);
  };

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Select a tenant to view health status.</p>
      </div>
    );
  }

  const healthyCt = connections.filter(
    (c) => c.health_status === "healthy",
  ).length;
  const degradedCt = connections.filter(
    (c) => c.health_status === "degraded",
  ).length;
  const unhealthyCt = connections.filter(
    (c) => c.health_status === "unhealthy",
  ).length;
  const unknownCt = connections.filter(
    (c) => c.health_status === "unknown",
  ).length;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">Health Matrix</h1>
        <p className="text-slate-400 mt-1">
          Real-time health status of all connected products
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card title="Healthy">
          <div className="text-3xl font-bold text-green-400">{healthyCt}</div>
        </Card>
        <Card title="Degraded">
          <div className="text-3xl font-bold text-yellow-400">{degradedCt}</div>
        </Card>
        <Card title="Unhealthy">
          <div className="text-3xl font-bold text-red-400">{unhealthyCt}</div>
        </Card>
        <Card title="Unknown">
          <div className="text-3xl font-bold text-slate-400">{unknownCt}</div>
        </Card>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-700 rounded" />
          ))}
        </div>
      ) : (
        <HealthGrid
          products={connections}
          onProductClick={handleProductClick}
        />
      )}
    </div>
  );
}

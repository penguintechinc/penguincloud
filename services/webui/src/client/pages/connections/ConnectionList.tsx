import { useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { useTenantStore } from "../../stores/tenantStore";
import { useProductsStore } from "../../stores/productsStore";
import Card from "../../components/Card";
import ProductStatusCard from "../../components/ProductStatusCard";
import type { ProductConnection } from "../../types";

export default function ConnectionList() {
  const { currentTenant } = useTenantStore();
  const { connections, fetchConnections, isLoading } = useProductsStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (currentTenant) {
      fetchConnections(currentTenant.id);
    }
  }, [currentTenant, fetchConnections]);

  const handleClick = (product: ProductConnection) => {
    navigate(`/connections/${product.id}`);
  };

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Select a tenant to manage connections.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">Connections</h1>
          <p className="text-slate-400 mt-1">
            Manage product connections for{" "}
            {currentTenant.display_name || currentTenant.name}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/connections/new" className="btn btn-primary">
            Add Connection
          </Link>
          <Link to="/connections/discover" className="btn btn-secondary">
            Auto-Discover
          </Link>
        </div>
      </div>

      {isLoading ? (
        <div className="animate-pulse grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-700 rounded" />
          ))}
        </div>
      ) : connections.length === 0 ? (
        <Card title="No Connections">
          <p className="text-slate-400 mb-4">
            No products are connected yet. Add a connection manually or run
            auto-discovery.
          </p>
          <div className="flex gap-2">
            <Link to="/connections/new" className="btn btn-primary">
              Add Connection
            </Link>
            <Link to="/connections/discover" className="btn btn-secondary">
              Auto-Discover
            </Link>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {connections.map((conn) => (
            <ProductStatusCard
              key={conn.id}
              product={conn}
              onClick={() => handleClick(conn)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

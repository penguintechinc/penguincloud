import { useState, useEffect } from 'react';
import { useTenantStore } from '../stores/tenantStore';
import { useProductsStore } from '../stores/productsStore';
import { dashboardApi } from '../hooks/useApi';
import Card from '../components/Card';
import HealthGrid from '../components/HealthGrid';
import { useNavigate } from 'react-router-dom';
import type { ProductConnection } from '../types';

export default function Health() {
  const { currentTenant } = useTenantStore();
  const { connections, fetchConnections } = useProductsStore();
  const navigate = useNavigate();
  const [healthData, setHealthData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!currentTenant) {
      setIsLoading(false);
      return;
    }

    const fetchData = async () => {
      setIsLoading(true);
      try {
        const [health] = await Promise.all([
          dashboardApi.health(currentTenant.id),
          fetchConnections(currentTenant.id),
        ]);
        setHealthData(health);
      } catch (err) {
        console.error('Failed to fetch health data:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [currentTenant, fetchConnections]);

  const handleProductClick = (product: ProductConnection) => {
    navigate(`/products/${product.id}`);
  };

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <p className="text-dark-400">Select a tenant to view health status.</p>
      </div>
    );
  }

  const healthyCt = connections.filter((c) => c.health_status === 'healthy').length;
  const degradedCt = connections.filter((c) => c.health_status === 'degraded').length;
  const unhealthyCt = connections.filter((c) => c.health_status === 'unhealthy').length;
  const unknownCt = connections.filter((c) => c.health_status === 'unknown').length;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gold-400">Health Matrix</h1>
        <p className="text-dark-400 mt-1">Real-time health status of all connected products</p>
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
          <div className="text-3xl font-bold text-dark-400">{unknownCt}</div>
        </Card>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 bg-dark-700 rounded" />
          ))}
        </div>
      ) : (
        <HealthGrid products={connections} onProductClick={handleProductClick} />
      )}
    </div>
  );
}

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { productsApi, proxyApi } from '../../hooks/useApi';
import Card from '../../components/Card';
import TabNavigation from '../../components/TabNavigation';
import type { ProductConnection, ProductManagementSchema } from '../../types';

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const [product, setProduct] = useState<ProductConnection | null>(null);
  const [schema, setSchema] = useState<ProductManagementSchema | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [proxyData, setProxyData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const [prod, mgmtSchema] = await Promise.all([
          productsApi.get(productId),
          productsApi.schema(productId).catch(() => null),
        ]);
        setProduct(prod);
        setSchema(mgmtSchema);
      } catch (err) {
        console.error('Failed to fetch product:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [productId]);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    ...(schema?.sections?.map((s) => ({ id: s.id, label: s.label })) || []),
  ];

  const handleProxyFetch = async (method: string, path: string) => {
    try {
      const result = await proxyApi.request(productId, method, path);
      setProxyData(result as Record<string, unknown>);
    } catch (err) {
      setProxyData({ error: err instanceof Error ? err.message : 'Request failed' });
    }
  };

  if (isLoading) return <div className="animate-pulse h-64 bg-dark-700 rounded" />;
  if (!product) return <p className="text-dark-400">Product not found.</p>;

  const statusColor: Record<string, string> = {
    healthy: 'text-green-400',
    degraded: 'text-yellow-400',
    unhealthy: 'text-red-400',
    unknown: 'text-dark-400',
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gold-400">{product.display_name}</h1>
        <p className="text-dark-400 mt-1">
          {product.product_type} —{' '}
          <span className={statusColor[product.health_status] || 'text-dark-400'}>
            {product.health_status}
          </span>
        </p>
      </div>

      <TabNavigation tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Product Info">
              <dl className="space-y-2">
                <div className="flex justify-between">
                  <dt className="text-dark-400">Type</dt>
                  <dd className="text-dark-200">{product.product_type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-dark-400">Base URL</dt>
                  <dd className="text-dark-200 truncate ml-4">{product.base_url}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-dark-400">Health</dt>
                  <dd className={statusColor[product.health_status]}>{product.health_status}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-dark-400">Last Check</dt>
                  <dd className="text-dark-200">
                    {product.last_health_check
                      ? new Date(product.last_health_check).toLocaleString()
                      : 'Never'}
                  </dd>
                </div>
              </dl>
            </Card>

            {schema && (
              <Card title="Capabilities">
                <div className="flex flex-wrap gap-2">
                  {schema.capabilities.map((cap) => (
                    <span key={cap} className="px-2 py-1 bg-dark-800 rounded text-sm text-dark-300">
                      {cap}
                    </span>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}

        {/* Dynamic schema-driven sections */}
        {schema?.sections
          ?.filter((s) => s.id === activeTab)
          .map((section) => (
            <Card key={section.id} title={section.label}>
              <p className="text-dark-400 mb-4">{section.description || `Manage ${section.label}`}</p>
              {section.endpoints?.map((endpoint) => (
                <button
                  key={endpoint.path}
                  onClick={() => handleProxyFetch(endpoint.method, endpoint.path)}
                  className="btn btn-secondary btn-sm mr-2 mb-2"
                >
                  {endpoint.label || `${endpoint.method} ${endpoint.path}`}
                </button>
              ))}
              {proxyData && (
                <pre className="mt-4 p-3 bg-dark-800 rounded text-sm text-dark-300 overflow-auto max-h-96">
                  {JSON.stringify(proxyData, null, 2)}
                </pre>
              )}
            </Card>
          ))}
      </div>
    </div>
  );
}

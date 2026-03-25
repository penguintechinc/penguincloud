import { useState, useEffect } from 'react';
import { proxyApi } from '../../../hooks/useApi';
import Card from '../../../components/Card';
import TabNavigation from '../../../components/TabNavigation';

interface SquawkProps {
  productId: number;
}

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'domains', label: 'Domains' },
  { id: 'queries', label: 'Query Log' },
  { id: 'ioc', label: 'IOC Feeds' },
];

export default function SquawkOverview({ productId }: SquawkProps) {
  const [activeTab, setActiveTab] = useState('overview');
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchData = async (path: string) => {
    setIsLoading(true);
    try {
      const result = await proxyApi.request(productId, 'GET', path);
      setData(result as Record<string, unknown>);
    } catch (err) {
      setData({ error: err instanceof Error ? err.message : 'Failed to fetch' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: 'api/v1/status',
      domains: 'api/v1/domains',
      queries: 'api/v1/queries',
      ioc: 'api/v1/ioc/feeds',
    };
    fetchData(paths[activeTab] || 'api/v1/status');
  }, [activeTab, productId]);

  return (
    <div>
      <TabNavigation tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {isLoading ? (
          <div className="animate-pulse h-48 bg-dark-700 rounded" />
        ) : activeTab === 'overview' ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Total Domains">
              <div className="text-3xl font-bold text-gold-400">
                {(data as any)?.total_domains ?? '—'}
              </div>
            </Card>
            <Card title="Queries Today">
              <div className="text-3xl font-bold text-gold-400">
                {(data as any)?.queries_today ?? '—'}
              </div>
            </Card>
            <Card title="Blocked">
              <div className="text-3xl font-bold text-red-400">
                {(data as any)?.blocked_today ?? '—'}
              </div>
            </Card>
          </div>
        ) : (
          <Card title={tabs.find((t) => t.id === activeTab)?.label || ''}>
            {data ? (
              <pre className="text-sm text-dark-300 overflow-auto max-h-96">
                {JSON.stringify(data, null, 2)}
              </pre>
            ) : (
              <p className="text-dark-400">No data available</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

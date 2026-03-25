import { useState, useEffect } from 'react';
import { proxyApi } from '../../../hooks/useApi';
import Card from '../../../components/Card';
import TabNavigation from '../../../components/TabNavigation';

interface DarwinProps {
  productId: number;
}

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'deployments', label: 'Deployments' },
];

export default function DarwinOverview({ productId }: DarwinProps) {
  const [activeTab, setActiveTab] = useState('overview');
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: 'api/v1/status',
      deployments: 'api/v1/deployments',
    };
    setIsLoading(true);
    proxyApi.request(productId, 'GET', paths[activeTab] || 'api/v1/status')
      .then((r) => setData(r as Record<string, unknown>))
      .catch((err) => setData({ error: err instanceof Error ? err.message : 'Failed' }))
      .finally(() => setIsLoading(false));
  }, [activeTab, productId]);

  return (
    <div>
      <TabNavigation tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
      <div className="mt-6">
        {isLoading ? (
          <div className="animate-pulse h-48 bg-dark-700 rounded" />
        ) : activeTab === 'overview' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Active Deployments">
              <div className="text-3xl font-bold text-gold-400">{(data as any)?.active_deployments ?? '—'}</div>
            </Card>
            <Card title="Evolutions">
              <div className="text-3xl font-bold text-gold-400">{(data as any)?.total_evolutions ?? '—'}</div>
            </Card>
          </div>
        ) : (
          <Card title={tabs.find((t) => t.id === activeTab)?.label || ''}>
            {data ? (
              <pre className="text-sm text-dark-300 overflow-auto max-h-96">{JSON.stringify(data, null, 2)}</pre>
            ) : (
              <p className="text-dark-400">No data available</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

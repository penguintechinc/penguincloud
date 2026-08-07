import { useState, useEffect, useCallback } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";
import { metric } from "../metric";

interface WaddleAIProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "keys", label: "API Keys" },
  { id: "models", label: "Models" },
  { id: "usage", label: "Usage" },
];

export default function WaddleAIOverview({ productId }: WaddleAIProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchData = useCallback(
    async (path: string) => {
      setIsLoading(true);
      try {
        const result = await proxyApi.request(productId, "GET", path);
        setData(result as Record<string, unknown>);
      } catch (err) {
        setData({
          error: err instanceof Error ? err.message : "Failed to fetch",
        });
      } finally {
        setIsLoading(false);
      }
    },
    [productId],
  );

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: "api/v1/status",
      keys: "api/v1/keys",
      models: "api/v1/models",
      usage: "api/v1/usage",
    };
    fetchData(paths[activeTab] || "api/v1/status");
  }, [activeTab, fetchData]);

  return (
    <div>
      <TabNavigation
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div className="mt-6">
        {isLoading ? (
          <div className="animate-pulse h-48 bg-slate-700 rounded" />
        ) : activeTab === "overview" ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Active API Keys">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "active_keys")}
              </div>
            </Card>
            <Card title="Models Available">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "models_available")}
              </div>
            </Card>
            <Card title="Requests (24h)">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "requests_24h")}
              </div>
            </Card>
          </div>
        ) : (
          <Card title={tabs.find((t) => t.id === activeTab)?.label || ""}>
            {data ? (
              <pre className="text-sm text-slate-300 overflow-auto max-h-96">
                {JSON.stringify(data, null, 2)}
              </pre>
            ) : (
              <p className="text-slate-400">No data available</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

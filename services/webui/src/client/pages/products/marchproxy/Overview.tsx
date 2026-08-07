import { useState, useEffect, useCallback } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";
import { metric } from "../metric";

interface MarchProxyProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "services", label: "Services" },
  { id: "clusters", label: "Clusters" },
  { id: "certs", label: "Certificates" },
];

export default function MarchProxyOverview({ productId }: MarchProxyProps) {
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
      services: "api/v1/services",
      clusters: "api/v1/clusters",
      certs: "api/v1/certificates",
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
            <Card title="Active Services">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "active_services")}
              </div>
            </Card>
            <Card title="Active Clusters">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "active_clusters")}
              </div>
            </Card>
            <Card title="Certificates">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "certificates")}
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

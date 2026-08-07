import { useState, useEffect } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";

interface SkausWatchProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "alerts", label: "Alerts" },
  { id: "threat", label: "Threat Intel" },
  { id: "edr", label: "EDR" },
];

export default function SkausWatchOverview({ productId }: SkausWatchProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchData = async (path: string) => {
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
  };

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: "api/v1/status",
      alerts: "api/v1/alerts",
      threat: "api/v1/threat-intel",
      edr: "api/v1/edr",
    };
    fetchData(paths[activeTab] || "api/v1/status");
  }, [activeTab, productId]);

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
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card title="Active Alerts">
              <div className="text-3xl font-bold text-red-400">
                {(data as any)?.active_alerts ?? "—"}
              </div>
            </Card>
            <Card title="Threats Detected">
              <div className="text-3xl font-bold text-yellow-400">
                {(data as any)?.threats_detected ?? "—"}
              </div>
            </Card>
            <Card title="Endpoints Monitored">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.endpoints_monitored ?? "—"}
              </div>
            </Card>
            <Card title="Events (24h)">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.events_24h ?? "—"}
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

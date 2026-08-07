import { useState, useEffect } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";

interface TobogganingProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "rollouts", label: "Rollouts" },
  { id: "pipelines", label: "Pipelines" },
];

export default function TobogganingOverview({ productId }: TobogganingProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: "api/v1/status",
      rollouts: "api/v1/rollouts",
      pipelines: "api/v1/pipelines",
    };
    setIsLoading(true);
    proxyApi
      .request(productId, "GET", paths[activeTab] || "api/v1/status")
      .then((r) => setData(r as Record<string, unknown>))
      .catch((err) =>
        setData({ error: err instanceof Error ? err.message : "Failed" }),
      )
      .finally(() => setIsLoading(false));
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Active Rollouts">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.active_rollouts ?? "—"}
              </div>
            </Card>
            <Card title="Pipelines">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.total_pipelines ?? "—"}
              </div>
            </Card>
            <Card title="Deployments (24h)">
              <div className="text-3xl font-bold text-green-400">
                {(data as any)?.deployments_24h ?? "—"}
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

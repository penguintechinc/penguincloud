import { useState, useEffect } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";
import { metric } from "../metric";

interface IceShelvesProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "buckets", label: "Buckets" },
  { id: "volumes", label: "Volumes" },
];

export default function IceShelvesOverview({ productId }: IceShelvesProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const paths: Record<string, string> = {
      overview: "api/v1/status",
      buckets: "api/v1/buckets",
      volumes: "api/v1/volumes",
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
            <Card title="Buckets">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "total_buckets")}
              </div>
            </Card>
            <Card title="Volumes">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "total_volumes")}
              </div>
            </Card>
            <Card title="Storage Used">
              <div className="text-3xl font-bold text-amber-400">
                {metric(data, "storage_used")}
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

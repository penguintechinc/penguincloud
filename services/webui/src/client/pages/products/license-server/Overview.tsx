import { useState, useEffect } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";

interface LicenseServerProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "licenses", label: "Licenses" },
  { id: "products", label: "Products" },
  { id: "orgs", label: "Organizations" },
];

export default function LicenseServerOverview({
  productId,
}: LicenseServerProps) {
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
      overview: "api/v2/status",
      licenses: "api/v2/licenses",
      products: "api/v2/products",
      orgs: "api/v2/organizations",
    };
    fetchData(paths[activeTab] || "api/v2/status");
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
            <Card title="Active Licenses">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.active_licenses ?? "—"}
              </div>
            </Card>
            <Card title="Products">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.total_products ?? "—"}
              </div>
            </Card>
            <Card title="Organizations">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.total_organizations ?? "—"}
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

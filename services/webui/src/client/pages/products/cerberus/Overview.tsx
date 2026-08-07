import { useState, useEffect } from "react";
import { proxyApi } from "../../../hooks/useApi";
import Card from "../../../components/Card";
import TabNavigation from "../../../components/TabNavigation";

interface CerberusProps {
  productId: number;
}

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "policies", label: "Policies" },
  { id: "sessions", label: "Sessions" },
  { id: "audit", label: "Auth Audit" },
];

export default function CerberusOverview({ productId }: CerberusProps) {
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
      policies: "api/v1/policies",
      sessions: "api/v1/sessions",
      audit: "api/v1/audit",
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
            <Card title="Active Policies">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.active_policies ?? "—"}
              </div>
            </Card>
            <Card title="Active Sessions">
              <div className="text-3xl font-bold text-amber-400">
                {(data as any)?.active_sessions ?? "—"}
              </div>
            </Card>
            <Card title="Auth Failures (24h)">
              <div className="text-3xl font-bold text-red-400">
                {(data as any)?.auth_failures_24h ?? "—"}
              </div>
            </Card>
            <Card title="MFA Enabled">
              <div className="text-3xl font-bold text-green-400">
                {(data as any)?.mfa_enabled_users ?? "—"}
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

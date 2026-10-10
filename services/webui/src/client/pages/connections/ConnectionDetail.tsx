import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { productsApi } from "../../hooks/useApi";
import Card from "../../components/Card";
import TabNavigation from "../../components/TabNavigation";
import type { ProductConnection } from "../../types";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "config", label: "Configuration" },
  { id: "health", label: "Health" },
];

export default function ConnectionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");
  const [connection, setConnection] = useState<ProductConnection | null>(null);
  const [healthData, setHealthData] = useState<Record<string, unknown> | null>(
    null,
  );
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);

  const connId = Number(id);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const conn = await productsApi.get(connId);
        setConnection(conn);
      } catch (err) {
        console.error("Failed to fetch connection:", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [connId]);

  useEffect(() => {
    if (activeTab === "health" && connId) {
      productsApi.health(connId).then(setHealthData).catch(console.error);
    }
  }, [activeTab, connId]);

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const result = await productsApi.test(connId);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        error: err instanceof Error ? err.message : "Test failed",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Remove this product connection?")) return;
    try {
      await productsApi.delete(connId);
      navigate("/connections");
    } catch (err) {
      console.error("Failed to delete connection:", err);
    }
  };

  const statusColor: Record<string, string> = {
    healthy: "text-green-400",
    degraded: "text-yellow-400",
    unhealthy: "text-red-400",
    unknown: "text-slate-400",
  };

  if (isLoading)
    return <div className="animate-pulse h-64 bg-slate-700 rounded" />;
  if (!connection)
    return <p className="text-slate-400">Connection not found.</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">
            {connection.display_name}
          </h1>
          <p className="text-slate-400 mt-1">
            {connection.product_type} —{" "}
            <span
              className={
                statusColor[connection.health_status] || "text-slate-400"
              }
            >
              {connection.health_status}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate(`/products/${connId}`)}
            className="btn btn-primary"
          >
            Manage
          </button>
          <button
            onClick={handleTest}
            disabled={isTesting}
            className="btn btn-secondary"
          >
            {isTesting ? "Testing..." : "Test Connection"}
          </button>
        </div>
      </div>

      {testResult && (
        <div className="mb-4 p-3 bg-slate-800 rounded border border-slate-700">
          <pre className="text-sm text-slate-300 overflow-auto">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        </div>
      )}

      <TabNavigation
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div className="mt-6">
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Connection Info">
              <dl className="space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Type</dt>
                  <dd className="text-slate-200">{connection.product_type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Base URL</dt>
                  <dd className="text-slate-200 truncate ml-4">
                    {connection.base_url}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Auth Type</dt>
                  <dd className="text-slate-200">{connection.auth_type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">API Version</dt>
                  <dd className="text-slate-200">
                    {connection.api_version || "default"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Discovered</dt>
                  <dd className="text-slate-200">
                    {connection.discovered ? "Yes" : "Manual"}
                  </dd>
                </div>
              </dl>
            </Card>
            <Card title="Status">
              <dl className="space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Health</dt>
                  <dd
                    className={
                      statusColor[connection.health_status] || "text-slate-400"
                    }
                  >
                    {connection.health_status}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Last Check</dt>
                  <dd className="text-slate-200">
                    {connection.last_health_check
                      ? new Date(connection.last_health_check).toLocaleString()
                      : "Never"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Active</dt>
                  <dd className="text-slate-200">
                    {connection.is_active ? "Yes" : "No"}
                  </dd>
                </div>
              </dl>
            </Card>
          </div>
        )}

        {activeTab === "config" && (
          <Card title="Configuration">
            <p className="text-slate-400 mb-4">
              Edit connection settings or remove this product.
            </p>
            <button onClick={handleDelete} className="btn btn-danger">
              Remove Connection
            </button>
          </Card>
        )}

        {activeTab === "health" && (
          <Card title="Health Details">
            {healthData ? (
              <pre className="text-sm text-slate-300 overflow-auto">
                {JSON.stringify(healthData, null, 2)}
              </pre>
            ) : (
              <p className="text-slate-400">Loading health data...</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

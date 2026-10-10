/**
 * Usage tab of the tenant detail page: current-vs-quota counters.
 */

import Card from "../../../components/Card";
import { useTenantUsage } from "../../../hooks/useTenants";

interface TenantUsageTabProps {
  tenantId: number;
}

export default function TenantUsageTab({ tenantId }: TenantUsageTabProps) {
  const usageQuery = useTenantUsage(tenantId);
  const usage = usageQuery.data;

  return (
    <Card title="Resource Usage">
      {usage ? (
        // Iterates the nested `usage` map rather than the top-level response:
        // the response also carries tenant_id and plan, and its `usage` value
        // is an object that previously rendered as "[object Object]".
        <div className="grid grid-cols-2 gap-4">
          {Object.entries(usage.usage).map(([key, quota]) => (
            <div key={key} className="p-3 bg-slate-800 rounded">
              <div className="text-sm text-slate-400">
                {key.replace(/_/g, " ")}
              </div>
              <div className="text-lg font-bold text-amber-400">
                {quota.current} / {quota.max}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-400">
          {usageQuery.isError
            ? "Failed to load usage data."
            : "Loading usage data..."}
        </p>
      )}
    </Card>
  );
}

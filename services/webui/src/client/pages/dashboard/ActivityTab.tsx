/**
 * Recent activity tab: the most recent audit entries for the active tenant.
 */

import Card from "../../components/Card";
import type { AuditLog } from "../../types";

interface ActivityTabProps {
  activity: AuditLog[];
  isLoading: boolean;
}

export default function ActivityTab({ activity, isLoading }: ActivityTabProps) {
  return (
    <Card title="Recent Activity">
      {isLoading ? (
        <div className="animate-pulse space-y-2" data-testid="activity-loading">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-8 bg-slate-700 rounded" />
          ))}
        </div>
      ) : activity.length > 0 ? (
        <div className="space-y-2">
          {activity.map((log) => (
            <div
              key={log.id}
              className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0"
            >
              <div>
                <span className="badge badge-viewer text-xs">{log.action}</span>
                <span className="text-sm text-slate-300 ml-2">
                  {log.resource_type}
                  {log.resource_id ? ` #${log.resource_id}` : ""}
                </span>
              </div>
              <span className="text-xs text-slate-500">
                {new Date(log.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-400">No recent activity</p>
      )}
    </Card>
  );
}

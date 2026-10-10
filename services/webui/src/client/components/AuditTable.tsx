/**
 * Paginated audit log table.
 * Rows come from TanStack Query keyed by tenant + page; only the current page
 * number is component state.
 */

import { useState } from "react";
import { useAuditLogs } from "../hooks/useAudit";

interface AuditTableProps {
  tenantId: number;
  limit?: number;
}

export default function AuditTable({ tenantId, limit = 50 }: AuditTableProps) {
  const [page, setPage] = useState(1);
  const logsQuery = useAuditLogs(tenantId, page, limit);

  const logs = logsQuery.data?.logs ?? [];
  const total = logsQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  if (logsQuery.isLoading) {
    return (
      <div className="animate-pulse space-y-2" data-testid="audit-loading">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-10 bg-slate-700 rounded" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="table w-full" data-testid="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Resource</th>
              <th>User</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="text-xs text-slate-400">
                  {new Date(log.created_at).toLocaleString()}
                </td>
                <td>
                  <span className="badge badge-viewer">{log.action}</span>
                </td>
                <td className="text-sm text-slate-300">
                  {log.resource_type}
                  {log.resource_id ? ` #${log.resource_id}` : ""}
                </td>
                <td className="text-sm text-slate-400">{log.user_id}</td>
                <td className="text-xs text-slate-500">{log.ip_address}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-slate-400 py-8">
                  {logsQuery.isError
                    ? "Failed to load audit logs"
                    : "No audit logs found"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-slate-400">
            Page {page} of {totalPages} ({total} total)
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="btn btn-secondary btn-sm focus:ring-2 focus:ring-sky-500"
            >
              Previous
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="btn btn-secondary btn-sm focus:ring-2 focus:ring-sky-500"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

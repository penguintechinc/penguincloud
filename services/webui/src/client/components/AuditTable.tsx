import { useState, useEffect } from 'react';
import api from '../lib/api';
import type { AuditLog } from '../types';

interface AuditTableProps {
  tenantId: number;
  limit?: number;
}

export default function AuditTable({ tenantId, limit = 50 }: AuditTableProps) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fetchLogs = async () => {
      setIsLoading(true);
      try {
        const response = await api.get('/audit/logs', {
          params: { tenant_id: tenantId, page, per_page: limit },
        });
        setLogs(response.data.logs);
        setTotal(response.data.total);
      } catch (err) {
        console.error('Failed to fetch audit logs:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchLogs();
  }, [tenantId, page, limit]);

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      {isLoading ? (
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-dark-700 rounded" />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="table w-full">
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
                  <td className="text-xs text-dark-400">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td>
                    <span className="badge badge-viewer">{log.action}</span>
                  </td>
                  <td className="text-sm text-dark-300">
                    {log.resource_type}{log.resource_id ? ` #${log.resource_id}` : ''}
                  </td>
                  <td className="text-sm text-dark-400">{log.user_id}</td>
                  <td className="text-xs text-dark-500">{log.ip_address}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center text-dark-400 py-8">
                    No audit logs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-dark-400">
            Page {page} of {totalPages} ({total} total)
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="btn btn-secondary btn-sm"
            >
              Previous
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="btn btn-secondary btn-sm"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Non-data views for DataTable: loading, error, and empty.
 *
 * Split out of DataTable to keep every kit file under the 5,000-character
 * house limit. Each carries the role/aria wiring assistive tech needs to
 * announce the state change.
 */
import { AlertCircle } from "lucide-react";

/** Skeleton rows shown while a query is in flight. */
export function DataTableLoading() {
  return (
    <div data-testid="datatable" className="w-full">
      <div
        role="status"
        aria-label="Loading table data"
        className="animate-pulse space-y-2"
      >
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-12 bg-slate-700 rounded" />
        ))}
      </div>
    </div>
  );
}

export interface DataTableErrorProps {
  error: Error;
  onRetry?: () => void;
}

/** Query failure, with an optional retry affordance. */
export function DataTableError({ error, onRetry }: DataTableErrorProps) {
  return (
    <div
      data-testid="datatable"
      role="alert"
      className="w-full bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded"
    >
      <div className="flex items-start gap-3">
        <AlertCircle size={20} className="shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold">Error loading data</p>
          <p className="text-sm mt-1">{error.message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-sm font-medium focus:ring-2 focus:ring-red-500 focus:ring-offset-2 focus:ring-offset-red-900"
              aria-label="Retry loading data"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Successful query that returned no rows. */
export function DataTableEmpty() {
  return (
    <div data-testid="datatable-empty" className="w-full text-center py-8">
      <p className="text-amber-400 font-medium">No data available</p>
    </div>
  );
}

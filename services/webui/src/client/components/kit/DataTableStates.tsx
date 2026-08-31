/**
 * Non-data views for DataTable: loading, error, stale-refetch, and empty.
 *
 * Split out of DataTable to keep every kit file under the 5,000-character
 * house limit. Each carries the role/aria wiring assistive tech needs to
 * announce the state change.
 */
import { AlertCircle } from "lucide-react";
import { describeQueryError } from "../../lib/mutationError";

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
  /** Overrides the generic "Error loading data" heading — see
   * `DataTableProps.errorTitle`'s doc for why this is optional and additive. */
  title?: string;
}

/**
 * Full-takeover query failure — rendered only when there is nothing else on
 * screen to preserve (see `DataTable`'s `error && data.length === 0`
 * branch): a genuine initial-load failure, or a refetch that failed with no
 * prior successful data to fall back to. `describeQueryError` applies the
 * same upstream-provenance sanitization the mutation banner uses, so a proxy
 * response marked `X-Portal-Upstream-Response` never renders its raw body
 * here either — see `lib/mutationError.ts`.
 */
export function DataTableError({
  error,
  onRetry,
  title = "Error loading data",
}: DataTableErrorProps) {
  return (
    <div
      data-testid="datatable"
      role="alert"
      className="w-full bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded"
    >
      <div className="flex items-start gap-3">
        <AlertCircle size={20} className="shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold">{title}</p>
          <p className="text-sm mt-1">{describeQueryError(error)}</p>
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

export interface DataTableStaleNoticeProps {
  error: Error;
  onRetry?: () => void;
}

/**
 * Quiet notice for a background refetch that failed while the table is
 * still showing the last successful data — deliberately NOT the same
 * red full-page takeover as `DataTableError`. Replacing already-rendered,
 * still-useful rows with a failure screen on every transient refetch blip
 * (window refocus, a flaky upstream) is worse than the bug this whole fix
 * addresses: it teaches an operator that a real, still-good screen is
 * broken. `role="status"` (polite) rather than `role="alert"`: the operator
 * already has usable data in front of them, so this does not need to
 * interrupt like an initial-load failure does.
 */
export function DataTableStaleNotice({
  error,
  onRetry,
}: DataTableStaleNoticeProps) {
  return (
    <div
      data-testid="datatable-stale-notice"
      role="status"
      className="w-full mb-2 flex items-center gap-3 bg-amber-950 border border-amber-700 text-amber-200 px-3 py-2 rounded text-sm"
    >
      <AlertCircle size={16} className="shrink-0" aria-hidden="true" />
      <p className="flex-1">
        Showing the last loaded data — refresh failed:{" "}
        {describeQueryError(error)}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 px-2 py-1 bg-amber-800 hover:bg-amber-700 text-amber-50 rounded text-xs font-medium focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 focus:ring-offset-amber-950"
          aria-label="Retry loading data"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export interface DataTableEmptyProps {
  /** Overrides the generic "No data available" copy — see
   * `DataTableProps.emptyMessage`'s doc for why this is optional and additive. */
  message?: string;
}

/** Successful query that returned no rows. */
export function DataTableEmpty({
  message = "No data available",
}: DataTableEmptyProps) {
  return (
    <div data-testid="datatable-empty" className="w-full text-center py-8">
      <p className="text-amber-400 font-medium">{message}</p>
    </div>
  );
}

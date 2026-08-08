import { useCancelOperation, useGoughOperations } from "./useGoughOperations";
import type { GoughOperation } from "./types";

/**
 * Colours for an operation's lifecycle state.
 *
 * Deliberately not the kit's StatusBadge: that component speaks the app-wide
 * HealthStatus vocabulary (healthy/degraded/unhealthy/unknown), and an
 * operation state is a different question — a `pending` deployment is not an
 * unhealthy one. Mapping between the two would put a red "unhealthy" badge
 * on a perfectly normal failed-then-retried run.
 */
const STATE_CLASSES: Record<string, string> = {
  succeeded: "bg-emerald-500/10 text-emerald-400",
  failed: "bg-red-500/10 text-red-400",
  cancelled: "bg-amber-500/10 text-amber-400",
  running: "bg-sky-500/10 text-sky-400",
  pending: "bg-slate-500/10 text-slate-400",
};

function OperationStateBadge({ operation }: { operation: GoughOperation }) {
  const classes =
    STATE_CLASSES[operation.state] ?? "bg-slate-500/10 text-slate-400";
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs ${classes}`}
      data-testid={`gough-operation-state-${operation.id}`}
    >
      {/* Gough's verbatim status, not the normalised state: the normalised
          value drives control flow, the raw one is what an operator can match
          against Gough's own UI. */}
      {operation.status || operation.state}
    </span>
  );
}

/**
 * Progress bar for one operation.
 *
 * Renders nothing when `progress` is null, which is the honest case rather
 * than a gap: a Gough deployment publishes only an unbounded `phase` integer,
 * so any bar drawn from it would be invented. An upgrade run publishes
 * nodes_completed/nodes_total and does get a bar.
 */
function ProgressBar({ progress }: { progress?: number | null }) {
  if (progress == null) return null;
  const pct = Math.max(0, Math.min(100, Math.round(progress * 100)));
  return (
    <div className="mt-1">
      <div
        className="h-1.5 bg-slate-700 rounded overflow-hidden"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Operation progress"
      >
        <div className="h-full bg-sky-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400">{pct}%</span>
    </div>
  );
}

function OperationRow({ operation }: { operation: GoughOperation }) {
  const cancel = useCancelOperation();

  return (
    <li
      className="py-3 border-b border-slate-700 last:border-b-0"
      data-testid={`gough-operation-${operation.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-amber-400 truncate">
              {operation.kind}
            </span>
            <OperationStateBadge operation={operation} />
          </div>
          {operation.detail && (
            <p className="text-xs text-slate-400 mt-1">{operation.detail}</p>
          )}
          {operation.error && (
            <p className="text-xs text-red-400 mt-1">{operation.error}</p>
          )}
          <ProgressBar progress={operation.progress} />
        </div>

        {!operation.is_terminal && (
          <button
            type="button"
            onClick={() =>
              cancel.mutate({
                kind: operation.kind,
                operationId: operation.id,
              })
            }
            disabled={cancel.isPending}
            data-testid={`gough-operation-cancel-${operation.id}`}
            className="px-2 py-1 text-xs rounded border border-slate-600 text-amber-500 hover:text-amber-400 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none disabled:opacity-50"
          >
            Cancel
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * Live operations for the tenant's Gough connection.
 *
 * The poll loop lives in `useGoughOperations` and stops when every operation
 * reports `is_terminal`, so a settled fleet costs no background traffic.
 */
export function OperationsPanel() {
  const { data, isLoading } = useGoughOperations();

  if (isLoading) {
    return (
      <div
        className="animate-pulse h-16 bg-slate-700 rounded"
        data-testid="gough-operations-loading"
      />
    );
  }

  if (!data || data.length === 0) return null;

  return (
    <section
      className="mb-6 bg-slate-800 border border-slate-700 rounded-lg p-4"
      aria-label="Running operations"
      data-testid="gough-operations"
    >
      <h2 className="text-sm font-semibold text-amber-400 mb-2">Operations</h2>
      <ul>
        {data.map((operation) => (
          <OperationRow key={operation.id} operation={operation} />
        ))}
      </ul>
    </section>
  );
}

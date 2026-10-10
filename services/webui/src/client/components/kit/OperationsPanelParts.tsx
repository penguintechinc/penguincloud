/**
 * Sub-renders for `OperationsPanel`: the state badge, progress bar,
 * produced-result list, and log-stream viewer. Split out to keep
 * `OperationsPanel.tsx` itself under the file-size guideline — the same
 * split `DataTableStates.tsx` is for `DataTable.tsx`.
 */
import type { OperationLike, OperationLogLine } from "./operationsPanelTypes";

/**
 * Colours for an operation's lifecycle state.
 *
 * Deliberately not the kit's `StatusBadge`: that component speaks the
 * app-wide HealthStatus vocabulary (healthy/degraded/unhealthy/unknown),
 * and an operation state is a different question — a `pending` deployment
 * is not an unhealthy one. Mapping between the two would put a red
 * "unhealthy" badge on a perfectly normal failed-then-retried run.
 */
const STATE_CLASSES: Record<string, string> = {
  succeeded: "bg-emerald-500/10 text-emerald-400",
  failed: "bg-red-500/10 text-red-400",
  cancelled: "bg-amber-500/10 text-amber-400",
  running: "bg-sky-500/10 text-sky-400",
  pending: "bg-slate-500/10 text-slate-400",
};

/**
 * An operation's lifecycle badge — the running/succeeded/failed/cancelled
 * distinction an operator reads at a glance. Renders the product's verbatim
 * `status` when present (what an operator can match against the product's
 * own UI); `state` is the fallback, never the primary — the normalised
 * value drives control flow, not display.
 */
export function OperationStateBadge({
  operation,
  testId,
}: {
  operation: OperationLike;
  testId: string;
}) {
  const classes =
    STATE_CLASSES[operation.state] ?? "bg-slate-500/10 text-slate-400";
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs ${classes}`}
      data-testid={testId}
    >
      {operation.status || operation.state}
    </span>
  );
}

/**
 * Progress bar for one operation.
 *
 * Renders nothing when `progress` is null, which is the honest case rather
 * than a gap: a product may publish only an unbounded phase counter, so any
 * bar drawn from it would be invented — see `Operation.progress`'s own doc
 * comment in `adapters/base.py`.
 */
export function ProgressBar({ progress }: { progress?: number | null }) {
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

/**
 * What a succeeded operation produced — the success counterpart of `error`.
 * A snapshot name, a restore target, a migration report: identified by more
 * than one field in general, which is why `result` is a dict rather than a
 * string. Renders nothing for an operation that produced no artefact.
 */
export function OperationResult({
  result,
}: {
  result: Record<string, unknown>;
}) {
  const entries = Object.entries(result).filter(
    ([, value]) => value !== null && value !== "",
  );
  if (entries.length === 0) return null;

  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-slate-400">{key}</dt>
          <dd className="text-slate-200 break-all">
            {typeof value === "object" ? JSON.stringify(value) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Severity colours for a log line's product-reported level. */
const LOG_LEVEL_CLASSES: Record<string, string> = {
  error: "text-red-400",
  warning: "text-amber-400",
  warn: "text-amber-400",
  debug: "text-slate-500",
};

/**
 * One operation's log stream, already fetched by the caller. This is a pure
 * render of `lines`/`isLoading`/`error` — the fetch itself is injected (see
 * `OperationsPanel`'s `useOperationLogs` prop), so this component has no
 * opinion on when a poll happens, only on how each of the four outcomes
 * (loading, errored, empty, populated) looks.
 */
export function OperationLogs({
  lines,
  isLoading,
  error,
  testIdPrefix,
  operationId,
}: {
  lines: OperationLogLine[] | undefined;
  isLoading: boolean;
  error: unknown;
  testIdPrefix: string;
  operationId: string;
}) {
  if (isLoading) {
    return (
      <div
        className="mt-2 h-12 bg-slate-700 rounded animate-pulse"
        data-testid={`${testIdPrefix}-operation-logs-loading-${operationId}`}
      />
    );
  }

  if (error) {
    return (
      <p
        className="mt-2 text-xs text-red-400"
        data-testid={`${testIdPrefix}-operation-logs-error-${operationId}`}
      >
        Could not load logs for this operation.
      </p>
    );
  }

  if (!lines || lines.length === 0) {
    return (
      <p
        className="mt-2 text-xs text-slate-400"
        data-testid={`${testIdPrefix}-operation-logs-empty-${operationId}`}
      >
        No log lines yet.
      </p>
    );
  }

  return (
    <ol
      className="mt-2 max-h-48 overflow-y-auto bg-slate-900 rounded p-2 space-y-0.5"
      data-testid={`${testIdPrefix}-operation-logs-${operationId}`}
    >
      {lines.map((line, index) => (
        <li
          key={`${line.timestamp ?? "t"}-${index}`}
          className="text-xs font-mono flex gap-2"
        >
          {line.timestamp && (
            <span className="text-slate-500 shrink-0">{line.timestamp}</span>
          )}
          {/* `level` is optional on the wire; default before indexing. */}
          <span
            className={
              LOG_LEVEL_CLASSES[line.level ?? "info"] ?? "text-slate-300"
            }
          >
            {line.message}
          </span>
        </li>
      ))}
    </ol>
  );
}

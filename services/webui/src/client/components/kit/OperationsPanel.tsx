/**
 * Generic operations panel — renders one product's live operations, fed
 * entirely by the typed operations API contract
 * (`services/portal-api/app/adapters/base.py`'s `Operation`/`OperationState`).
 *
 * Replaces two hand-written, product-specific panels
 * (`pages/products/gough/OperationsPanel.tsx`,
 * `pages/products/nest/NestOperationsPanel.tsx`) that did the same job
 * against the same contract with a different capability subset — Gough
 * offers cancel and a log-stream disclosure; Nest's product has no route
 * for either. This component takes that difference as data
 * (`OperationsPanelSpec`), not as a second implementation.
 *
 * Deliberately does NOT own polling. Gough discovers its operations via a
 * LIST route (`useGoughOperations`); Nest has no such collection and
 * watches only the ids it started (`useNestOperationWatch`) — a genuine
 * difference in what there is to poll, not glue duplicated by accident.
 * Both hooks already stop polling via TanStack Query's own
 * `refetchInterval` returning `false` once every watched operation reports
 * `is_terminal`, and both unsubscribe automatically on unmount — neither
 * uses a manual `setInterval` for there to be anything to leak. This panel
 * is handed the already-polled `operations` array and stays a render of that
 * state; the one timer-bearing thing it DOES own is the per-row log
 * stream, which only mounts (and so only starts fetching) once an operator
 * opens it, and unmounts — stopping it — the moment they close it or the
 * row leaves the list. See `OperationLogsSection` below.
 */
import { useState } from "react";
import {
  OperationLogs,
  OperationResult,
  OperationStateBadge,
  ProgressBar,
} from "./OperationsPanelParts";
import { describeOperationError } from "../../lib/mutationError";
import type {
  OperationLike,
  OperationsPanelSpec,
  UseOperationLogsResult,
} from "./operationsPanelTypes";

export type {
  OperationLike,
  OperationLogLine,
  OperationsPanelSpec,
  UseOperationLogsResult,
} from "./operationsPanelTypes";

type UseOperationLogsHook = (
  kind: string,
  operationId: string,
  options: { enabled: boolean; isTerminal: boolean },
) => UseOperationLogsResult;

/**
 * Mounted only while an operator has a row's logs open. Calling the
 * injected hook unconditionally inside its OWN body (rather than
 * conditionally inside `OperationRow`) keeps every hook call unconditional
 * per rules-of-hooks; conditional MOUNTING of this whole component is what
 * makes the fetch itself lazy — an operator who never opens logs for a
 * panel listing ten operations costs zero log requests, and closing (or
 * the row disappearing on the next poll) unmounts this and lets whatever
 * the injected hook does clean itself up.
 */
function OperationLogsSection({
  operation,
  testIdPrefix,
  useOperationLogs,
}: {
  operation: OperationLike;
  testIdPrefix: string;
  useOperationLogs: UseOperationLogsHook;
}) {
  const { data, isLoading, error } = useOperationLogs(
    operation.kind,
    operation.id,
    { enabled: true, isTerminal: operation.is_terminal },
  );
  return (
    <OperationLogs
      lines={data}
      isLoading={isLoading}
      error={error}
      testIdPrefix={testIdPrefix}
      operationId={operation.id}
    />
  );
}

interface OperationRowProps<TOperation extends OperationLike> {
  operation: TOperation;
  spec: OperationsPanelSpec;
  onCancel?: (operation: TOperation) => void;
  isCancelling?: (operation: TOperation) => boolean;
  useOperationLogs?: UseOperationLogsHook;
}

function OperationRow<TOperation extends OperationLike>({
  operation,
  spec,
  onCancel,
  isCancelling,
  useOperationLogs,
}: OperationRowProps<TOperation>) {
  const [showLogs, setShowLogs] = useState(false);
  const sanitizedError = describeOperationError(operation.error);
  const detailLine =
    operation.detail || operation.resource_id
      ? [operation.detail, operation.resource_id].filter(Boolean).join(" · ")
      : null;

  return (
    <li
      className="py-3 border-b border-slate-700 last:border-b-0"
      data-testid={`${spec.testIdPrefix}-operation-${operation.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-amber-400 truncate">
              {operation.kind}
            </span>
            <OperationStateBadge
              operation={operation}
              testId={`${spec.testIdPrefix}-operation-state-${operation.id}`}
            />
          </div>
          {detailLine && (
            <p className="text-xs text-slate-400 mt-1">{detailLine}</p>
          )}
          {sanitizedError && (
            <p
              className="text-xs text-red-400 mt-1"
              data-testid={`${spec.testIdPrefix}-operation-error-${operation.id}`}
            >
              {sanitizedError}
            </p>
          )}
          {operation.result && <OperationResult result={operation.result} />}
          <ProgressBar progress={operation.progress} />

          {spec.showLogs && useOperationLogs && (
            <>
              <button
                type="button"
                onClick={() => setShowLogs((open) => !open)}
                aria-expanded={showLogs}
                aria-controls={`${spec.testIdPrefix}-operation-logs-${operation.id}`}
                data-testid={`${spec.testIdPrefix}-operation-logs-toggle-${operation.id}`}
                className="mt-2 text-xs text-sky-400 hover:text-sky-300 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none rounded"
              >
                {showLogs ? "Hide logs" : "Show logs"}
              </button>
              {showLogs && (
                <OperationLogsSection
                  operation={operation}
                  testIdPrefix={spec.testIdPrefix}
                  useOperationLogs={useOperationLogs}
                />
              )}
            </>
          )}
        </div>

        {spec.cancelAllowed && !operation.is_terminal && onCancel && (
          <button
            type="button"
            onClick={() => onCancel(operation)}
            disabled={isCancelling?.(operation) ?? false}
            data-testid={`${spec.testIdPrefix}-operation-cancel-${operation.id}`}
            className="px-2 py-1 text-xs rounded border border-slate-600 text-amber-500 hover:text-amber-400 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none disabled:opacity-50"
          >
            Cancel
          </button>
        )}
      </div>
    </li>
  );
}

export interface OperationsPanelProps<TOperation extends OperationLike> {
  operations: TOperation[];
  /** True while the caller's own list/watch query has not yet resolved. */
  isLoading?: boolean;
  spec: OperationsPanelSpec;
  /** Required when `spec.cancelAllowed` is true; ignored otherwise. */
  onCancel?: (operation: TOperation) => void;
  isCancelling?: (operation: TOperation) => boolean;
  /** Required when `spec.showLogs` is true; ignored otherwise. */
  useOperationLogs?: UseOperationLogsHook;
}

/**
 * Live operations for one product connection.
 *
 * Hidden entirely when there is nothing to show — the contract both
 * predecessors already had. An empty panel would assert "the product is
 * idle", which neither a LIST-backed collection (Gough) nor a
 * watched-id set (Nest) can promise: Gough's list may simply be a page
 * that has not loaded yet, and Nest exposes no collection at all, so
 * "nothing watched" only ever means "nothing was started from this screen
 * in this session".
 */
export function OperationsPanel<TOperation extends OperationLike>({
  operations,
  isLoading = false,
  spec,
  onCancel,
  isCancelling,
  useOperationLogs,
}: OperationsPanelProps<TOperation>) {
  if (isLoading) {
    return (
      <div
        className="animate-pulse h-16 bg-slate-700 rounded"
        data-testid={`${spec.testIdPrefix}-operations-loading`}
      />
    );
  }

  if (operations.length === 0) return null;

  return (
    <section
      className="mb-6 bg-slate-800 border border-slate-700 rounded-lg p-4"
      aria-label={spec.title}
      aria-live="polite"
      data-testid={`${spec.testIdPrefix}-operations`}
    >
      <h2 className="text-sm font-semibold text-amber-400 mb-2">
        {spec.title}
      </h2>
      <ul>
        {operations.map((operation) => (
          <OperationRow
            key={operation.id}
            operation={operation}
            spec={spec}
            onCancel={onCancel}
            isCancelling={isCancelling}
            useOperationLogs={useOperationLogs}
          />
        ))}
      </ul>
    </section>
  );
}

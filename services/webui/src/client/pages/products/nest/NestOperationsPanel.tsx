import { useEffect } from "react";
import type { NestOperation } from "./types";
import { useRefetchOnSettled } from "./useNestOperations";

/** Nest reports a phase and nothing countable, so there is no progress bar. */
const STATE_STYLES: Record<string, string> = {
  succeeded: "text-emerald-400",
  failed: "text-red-400",
  running: "text-sky-400",
  pending: "text-amber-400",
};

/**
 * Renders what a finished operation produced.
 *
 * `result` is the success counterpart of `error` and the reason the contract
 * carries it: a snapshot, restore or migrate finishes by PRODUCING something —
 * the snapshot name, the restored PVC, the migration report. Without it the UI
 * would have to refetch the resource and guess which change was the one it
 * started.
 */
function OperationResult({ result }: { result: Record<string, unknown> }) {
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

/** One watched operation. */
function OperationRow({ operation }: { operation: NestOperation }) {
  const refetchOnSettled = useRefetchOnSettled();

  useEffect(() => {
    refetchOnSettled(operation);
  }, [operation, refetchOnSettled]);

  return (
    <li
      className="border border-slate-700 rounded p-3"
      data-testid={`nest-operation-${operation.id}`}
    >
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm text-slate-200">
          {operation.detail ?? operation.kind}
          {operation.resource_id ? ` · ${operation.resource_id}` : ""}
        </span>
        <span
          className={`text-xs ${STATE_STYLES[operation.state] ?? "text-slate-400"}`}
        >
          {operation.status}
        </span>
      </div>
      {operation.error ? (
        <p
          className="mt-2 text-xs text-red-400"
          data-testid={`nest-operation-error-${operation.id}`}
        >
          {operation.error}
        </p>
      ) : null}
      {operation.result ? <OperationResult result={operation.result} /> : null}
    </li>
  );
}

/**
 * The operations this screen started, polled until each is terminal.
 *
 * Hidden when empty rather than showing an empty panel: Nest exposes no
 * operation collection at this service, so "nothing here" means "nothing was
 * started from this page in this session" — not "the product is idle", and a
 * standing empty panel would assert the latter.
 */
export function NestOperationsPanel({
  operations,
}: {
  operations: NestOperation[];
}) {
  if (operations.length === 0) return null;

  return (
    <section className="mb-6" data-testid="nest-operations">
      <h2 className="text-sm font-semibold text-amber-500 mb-2">
        Operations in progress
      </h2>
      <ul className="space-y-2">
        {operations.map((operation) => (
          <OperationRow key={operation.id} operation={operation} />
        ))}
      </ul>
    </section>
  );
}

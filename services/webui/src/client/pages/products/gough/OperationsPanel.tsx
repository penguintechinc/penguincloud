import { OperationsPanel as KitOperationsPanel } from "../../../components/kit/OperationsPanel";
import type { OperationsPanelSpec } from "../../../components/kit/operationsPanelTypes";
import {
  useCancelOperation,
  useGoughOperations,
  useOperationLogs,
} from "./useGoughOperations";
import type { GoughOperation } from "./types";

/**
 * Gough's operations panel — a thin adapter wiring the kit's generic
 * `OperationsPanel` to Gough's own data hooks (`useGoughOperations.ts`).
 * Rendering, state-distinguishing, and error sanitization now all live in
 * the kit component; this file's only job is product-specific plumbing —
 * which operations to fetch, what a cancel click calls, what fetches one
 * operation's log lines.
 */
const SPEC: OperationsPanelSpec = {
  title: "Operations",
  testIdPrefix: "gough",
  cancelAllowed: true,
  showLogs: true,
  // Matches OPERATION_POLL_MS in useGoughOperations.ts — the panel itself
  // does not poll (see the kit component's module doc); this is echoed
  // here only so the descriptor is complete for a future manifest.
  pollIntervalMs: 3000,
};

/**
 * Live operations for the tenant's Gough connection.
 *
 * The poll loop lives in `useGoughOperations` and stops when every
 * operation reports `is_terminal`, so a settled fleet costs no background
 * traffic.
 */
export function OperationsPanel() {
  const { data, isLoading } = useGoughOperations();
  const cancel = useCancelOperation();

  return (
    <KitOperationsPanel<GoughOperation>
      operations={data ?? []}
      isLoading={isLoading}
      spec={SPEC}
      onCancel={(operation) =>
        cancel.mutate({ kind: operation.kind, operationId: operation.id })
      }
      // Scoped to "any cancel in flight", matching the mutation this
      // replaces: `useCancelOperation` is one mutation shared by every row,
      // not one per operation id.
      isCancelling={() => cancel.isPending}
      useOperationLogs={useOperationLogs}
    />
  );
}

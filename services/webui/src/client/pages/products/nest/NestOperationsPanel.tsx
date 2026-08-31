import { useEffect } from "react";
import { OperationsPanel as KitOperationsPanel } from "../../../components/kit/OperationsPanel";
import type { OperationsPanelSpec } from "../../../components/kit/operationsPanelTypes";
import type { NestOperation } from "./types";
import { useRefetchOnSettled } from "./useNestOperations";

/**
 * Nest's operations panel — a thin adapter wiring the kit's generic
 * `OperationsPanel` to the operations `useNestOperationWatch` already
 * resolved for `DatabasesPage`. Nest offers neither cancel (no cancel
 * route exists for this product) nor a log-stream disclosure (no log route
 * either) — both are `false` in Nest's spec, data the kit component reads,
 * rather than UI this file has to omit by hand.
 */
const SPEC: OperationsPanelSpec = {
  title: "Operations in progress",
  testIdPrefix: "nest",
  cancelAllowed: false,
  showLogs: false,
  // Matches OPERATION_POLL_MS in useNestOperations.ts — see Gough's
  // OperationsPanel.tsx for why this is carried even though the panel
  // itself does not poll.
  pollIntervalMs: 3000,
};

/**
 * Invalidates the databases/snapshots lists once one watched operation
 * settles. Not something the kit's generic row can own — it is Nest's own
 * "writes finish out of band" glue (see `useRefetchOnSettled`'s doc
 * comment), not a rendering concern, and Gough has no equivalent because
 * its resource lists refresh from `is_terminal` differently. Kept as a
 * standalone, render-nothing component so its `useEffect` fires with
 * exactly the same per-operation identity and dependency array the
 * original inline effect had.
 */
function NestOperationSettleEffect({
  operation,
}: {
  operation: NestOperation;
}) {
  const refetchOnSettled = useRefetchOnSettled();

  useEffect(() => {
    refetchOnSettled(operation);
  }, [operation, refetchOnSettled]);

  return null;
}

/**
 * The operations this screen started, polled until each is terminal.
 *
 * Hidden when empty rather than showing an empty panel: Nest exposes no
 * operation collection at this service, so "nothing here" means "nothing
 * was started from this page in this session" — not "the product is
 * idle", and a standing empty panel would assert the latter.
 */
export function NestOperationsPanel({
  operations,
}: {
  operations: NestOperation[];
}) {
  return (
    <>
      {operations.map((operation) => (
        <NestOperationSettleEffect key={operation.id} operation={operation} />
      ))}
      <KitOperationsPanel<NestOperation> operations={operations} spec={SPEC} />
    </>
  );
}

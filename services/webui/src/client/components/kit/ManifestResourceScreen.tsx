/**
 * Generic manifest-driven list screen: given a `ResourceDescriptor`, renders
 * the same shell every hand-written product screen used (`ProductScreen` +
 * `useProductResource` + `DataTable`), with columns, cells, and empty/error
 * copy all read from the manifest instead of a hand-written column file.
 *
 * Gated on the `penguincloud.declarative_console` flag (default-on).
 * `__tests__/ManifestResourceScreen.equivalence.test.tsx` proved this
 * component reproduced Gough's hand-written `NodesPage`/`BiomesPage`/
 * `AgentsPage` rendered tables exactly before Phase 8 Step 7 deleted them in
 * favour of this renderer — the equivalence fixtures remain as the
 * still-committed proof.
 *
 * Schema v2 lets this component render what schema v1 explicitly deferred:
 * - **Detail + row-actions** (`ManifestResourceDetail.tsx`) — gated on
 *   `resource.item_path`, schema v2's proof that this resource kind has a
 *   real, individually addressable item route.
 * - **Create** (`ManifestCreateForm.tsx`) — `resource.create` bound to
 *   react-libs' real `FormBuilder`, not an approximation.
 * - **Operations cancel/logs** — `manifest.operations.cancel_allowed`/
 *   `.show_logs`, both server-verified against the adapter's real
 *   capabilities by `validate_manifest`.
 * - **Operations `mode="watch"`** (Nest-convergence) — a resource whose
 *   product has no operation collection (`list_operations` 501s) mounts a
 *   panel fed by `useManifestOperationWatch` instead of `useManifestOperations`,
 *   watching only the ids `ManifestCreateForm`/`ManifestResourceDetail` report
 *   starting. `mode="list"` (the default, and every resource this component
 *   already rendered before this field existed) keeps the original
 *   collection-polled path untouched.
 */
import { useMemo } from "react";
import { ProductScreen } from "./ProductScreen";
import { DataTable, type ColumnConfig } from "./DataTable";
import { OperationsPanel } from "./OperationsPanel";
import { useProductResource } from "./useProductResource";
import {
  useCancelManifestOperation,
  useManifestOperationLogs,
  useManifestOperations,
} from "./useManifestOperations";
import { useManifestOperationWatch } from "./useManifestOperationWatch";
import { type ManifestRow } from "./manifestCells";
import { buildManifestListFetcher } from "./manifestListFetcher";
import { ManifestResourceDetail } from "./ManifestResourceDetail";
import { ManifestCreateForm } from "./ManifestCreateForm";
import { renderCellSlot } from "../extensions/ExtensionCellSlot";
import { queryKeys } from "../../api/keys";
import type { ConsoleManifest, ResourceDescriptor } from "./manifestTypes";
import type { OperationLike } from "./operationsPanelTypes";

export interface ManifestResourceScreenProps {
  /** Drives the feature/connection gate and every generated test id — the
   * same key `useProductEnabled`/`useProductConnection` already use. */
  productType: string;
  productLabel: string;
  manifest: ConsoleManifest;
  resource: ResourceDescriptor;
}

/** A row normalised the way `DataTable` requires: a string `id`, derived
 * from whichever field the resource itself names as its id — NOT hardcoded
 * to `"id"`, since e.g. Gough addresses agents by `agent_id`. */
function withStringId(
  row: ManifestRow,
  idField: string,
): ManifestRow & { id: string } {
  return { ...row, id: String(row[idField] ?? "") };
}

function buildColumns(
  productType: string,
  manifest: ConsoleManifest,
  resource: ResourceDescriptor,
): ColumnConfig<ManifestRow & { id: string }>[] {
  return resource.columns.map((column) => ({
    key: column.field as keyof (ManifestRow & { id: string }),
    label: column.label,
    sortable: column.sortable,
    render: (_value, row) =>
      renderCellSlot(
        productType,
        manifest.extensions,
        resource.kind,
        column,
        row,
      ),
  }));
}

export function ManifestResourceScreen({
  productType,
  productLabel,
  manifest,
  resource,
}: ManifestResourceScreenProps) {
  const list = resource.list;

  const fetcher = useMemo(
    () => (list ? buildManifestListFetcher(list) : async () => []),
    [list],
  );
  const columns = useMemo(
    () => buildColumns(productType, manifest, resource),
    [productType, manifest, resource],
  );

  const {
    data,
    isLoading,
    error,
    productId,
    tenantId,
    isConnectionLoading,
    refetch,
  } = useProductResource<ManifestRow>({
    productType,
    kind: resource.kind,
    queryKeyPrefix: queryKeys.consoleManifestResource(productType),
    fetcher,
  });

  const operationsSpec = manifest.operations;
  const isWatchMode = operationsSpec?.mode === "watch";
  const operations = useManifestOperations(
    tenantId,
    productId,
    operationsSpec !== null && operationsSpec !== undefined && !isWatchMode,
    (operationsSpec?.poll_interval_seconds ?? 5) * 1000,
  );
  const cancelOperation = useCancelManifestOperation(tenantId, productId);
  const useOperationLogsForResource = (
    kind: string,
    operationId: string,
    options: { enabled: boolean; isTerminal: boolean },
  ) =>
    useManifestOperationLogs(tenantId, productId, kind, operationId, options);

  // Always called (rules of hooks); gated internally on `isWatchMode` the
  // same way `useManifestOperations` above is gated on `!isWatchMode` — a
  // `mode="list"` resource never registers a watched id (nothing ever calls
  // `watch()` on this path), so the extra queries never fire.
  const watchOperations = useManifestOperationWatch(
    productType,
    tenantId,
    productId,
    resource.kind,
    isWatchMode && productId !== undefined,
    (operationsSpec?.poll_interval_seconds ?? 5) * 1000,
  );

  const rows = (data ?? []).map((row) => withStringId(row, resource.id_field));

  return (
    <ProductScreen
      productType={productType}
      productLabel={productLabel}
      title={resource.plural_label}
      description={`${resource.plural_label} for this connection.`}
      productId={productId}
      isConnectionLoading={isConnectionLoading}
      noConnectionReason={`manage its ${resource.plural_label.toLowerCase()}.`}
    >
      {operationsSpec && !isWatchMode && (
        <OperationsPanel<OperationLike>
          operations={operations.data ?? []}
          isLoading={operations.isLoading}
          spec={{
            title: operationsSpec.label,
            testIdPrefix: `${productType}-manifest-${resource.kind}`,
            cancelAllowed: operationsSpec.cancel_allowed,
            showLogs: operationsSpec.show_logs,
            pollIntervalMs: operationsSpec.poll_interval_seconds * 1000,
          }}
          onCancel={(operation) =>
            cancelOperation.mutate({
              kind: operation.kind,
              operationId: operation.id,
            })
          }
          isCancelling={() => cancelOperation.isPending}
          useOperationLogs={useOperationLogsForResource}
        />
      )}

      {operationsSpec && isWatchMode && (
        <OperationsPanel<OperationLike>
          operations={watchOperations.operations}
          spec={{
            title: operationsSpec.label,
            testIdPrefix: `${productType}-manifest-${resource.kind}`,
            // Structurally false for mode="watch" — validated server-side
            // (`OperationsSpec.__post_init__`), not re-derived from
            // `operationsSpec.cancel_allowed`/`.show_logs` here: a watched
            // operation has no collection to cancel from and no log route.
            cancelAllowed: false,
            showLogs: false,
            pollIntervalMs: operationsSpec.poll_interval_seconds * 1000,
          }}
        />
      )}

      <ManifestCreateForm
        productType={productType}
        tenantId={tenantId}
        productId={productId}
        resource={resource}
        watch={watchOperations.watch}
      />

      {list ? (
        <DataTable<ManifestRow & { id: string }>
          columns={columns}
          data={rows}
          isLoading={isLoading}
          error={error as Error | null}
          onRetry={() => void refetch()}
          emptyMessage={resource.empty_state}
          errorTitle={resource.error_state}
          caption={`${productLabel} ${resource.plural_label}`}
        />
      ) : (
        <p
          className="text-slate-400 text-sm"
          data-testid={`${productType}-${resource.kind}-no-list`}
        >
          {resource.label} has no list endpoint in this manifest version.
        </p>
      )}

      <ManifestResourceDetail
        productType={productType}
        tenantId={tenantId}
        productId={productId}
        manifest={manifest}
        resource={resource}
        rows={rows}
        watch={watchOperations.watch}
      />
    </ProductScreen>
  );
}

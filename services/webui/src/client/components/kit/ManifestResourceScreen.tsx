/**
 * Generic manifest-driven list screen: given a `ResourceDescriptor`, renders
 * the same shell every hand-written product screen uses (`ProductScreen` +
 * `useProductResource` + `DataTable`), with columns, cells, and empty/error
 * copy all read from the manifest instead of a hand-written column file.
 *
 * Behind the `penguincloud.declarative_console` flag, run ALONGSIDE the
 * hand-written product screens — this step does not convert or delete any
 * of them (see the module doc on `pages/products/gough/NodesPage.tsx`).
 * `__tests__/ManifestResourceScreen.equivalence.test.tsx` proves this
 * component reproduces `NodesPage`'s (and, where practical, `BiomesPage`'s/
 * `AgentsPage`'s) rendered table exactly.
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
import { renderCell, type ManifestRow } from "./manifestCells";
import { buildManifestListFetcher } from "./manifestListFetcher";
import { ManifestResourceDetail } from "./ManifestResourceDetail";
import { ManifestCreateForm } from "./ManifestCreateForm";
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
  resource: ResourceDescriptor,
): ColumnConfig<ManifestRow & { id: string }>[] {
  return resource.columns.map((column) => ({
    key: column.field as keyof (ManifestRow & { id: string }),
    label: column.label,
    sortable: column.sortable,
    render: (_value, row) => renderCell(column, row),
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
  const columns = useMemo(() => buildColumns(resource), [resource]);

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
  const operations = useManifestOperations(
    tenantId,
    productId,
    operationsSpec !== null && operationsSpec !== undefined,
    (operationsSpec?.poll_interval_seconds ?? 5) * 1000,
  );
  const cancelOperation = useCancelManifestOperation(tenantId, productId);
  const useOperationLogsForResource = (
    kind: string,
    operationId: string,
    options: { enabled: boolean; isTerminal: boolean },
  ) =>
    useManifestOperationLogs(tenantId, productId, kind, operationId, options);

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
      {operationsSpec && (
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

      <ManifestCreateForm
        productType={productType}
        tenantId={tenantId}
        productId={productId}
        resource={resource}
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
        resource={resource}
        rows={rows}
      />
    </ProductScreen>
  );
}

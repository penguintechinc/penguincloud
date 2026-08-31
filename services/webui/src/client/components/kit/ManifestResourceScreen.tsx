/**
 * Generic manifest-driven list screen: given a `ResourceDescriptor`, renders
 * the same shell every hand-written product screen uses (`ProductScreen` +
 * `useProductResource` + `DataTable`), with columns, cells, and empty/error
 * copy all read from the manifest instead of a hand-written column file.
 *
 * Behind the `penguincloud.declarative_console` flag, run ALONGSIDE the
 * hand-written product screens — Phase 8 Step 3 does not convert or delete
 * any of them (see the module doc on `pages/products/gough/NodesPage.tsx`).
 * `__tests__/ManifestResourceScreen.equivalence.test.tsx` is the
 * falsification test proving this component reproduces `NodesPage`'s
 * rendered table for Gough's `nodes` resource.
 *
 * Deliberately does NOT render row actions, a detail drawer, or a create
 * form:
 * - Row actions / detail need an ITEM path (`{list.path_bytes}{id}`), which
 *   `ResourceDescriptor`'s own docstring says this schema version does NOT
 *   derive and does not declare a field for — see the Step 3 report's
 *   "item-path" finding. String-munging one here would reproduce exactly
 *   the trailing-slash defect class `goughPaths.ts` exists to prevent
 *   (`biome_groups`' collection path has no trailing slash;
 *   `{path}{id}` concatenation would silently produce `.../groups42`).
 * - Create needs `FormSpec` bound to a real `@penguintechinc/react-libs`
 *   `FieldConfig` — see the shape mismatch documented at the bottom of
 *   `manifestTypes.ts`.
 *
 * Both are deferred to a follow-up step, not guessed at here.
 */
import { useMemo } from "react";
import { ProductScreen } from "./ProductScreen";
import { DataTable, type ColumnConfig } from "./DataTable";
import { OperationsPanel } from "./OperationsPanel";
import { useProductResource } from "./useProductResource";
import { useManifestOperations } from "./useManifestOperations";
import { renderCell, type ManifestRow } from "./manifestCells";
import { buildManifestListFetcher } from "./manifestListFetcher";
import { queryKeys } from "../../api/keys";
import type { ConsoleManifest, ResourceDescriptor } from "./manifestTypes";

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
        <OperationsPanel
          operations={operations.data ?? []}
          isLoading={operations.isLoading}
          spec={{
            title: operationsSpec.label,
            testIdPrefix: `${productType}-manifest-${resource.kind}`,
            // Neither capability is expressible on OperationsSpec yet — see
            // this file's module doc and `useManifestOperations.ts`.
            cancelAllowed: false,
            showLogs: false,
            pollIntervalMs: operationsSpec.poll_interval_seconds * 1000,
          }}
        />
      )}

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
    </ProductScreen>
  );
}

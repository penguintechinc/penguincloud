/**
 * One `RelationshipSpec` rendered as a child-list detail tab.
 *
 * `RelationshipSpec{child_kind, parent_field}` means "list `child_kind`
 * rows whose `parent_field` equals the open parent row's own identifier" —
 * mirrors Nest's `snapshot.parent_id == database.id` edge
 * (`app/adapters/nest/mapping.py`'s `to_resource`: a VolumeSnapshot's
 * `sourcePVC` becomes `Resource.parent_id`, and a DataResource's `Resource.id`
 * IS its name, the same value `sourcePVC` names), but nothing here names
 * Nest, databases, or snapshots — `child_kind`, `parent_field`, and the
 * open row's `id` are the only inputs, exactly as the schema declares them.
 *
 * Reuses the SAME mechanics the resource's own top-level list uses:
 * `buildManifestListFetcher` + `useProductResource` for the fetch,
 * `renderCell` for each column — no second rendering path to keep in sync.
 */
import { useMemo } from "react";
import { DataTable, type ColumnConfig } from "./DataTable";
import { useProductResource } from "./useProductResource";
import { buildManifestListFetcher } from "./manifestListFetcher";
import { renderCell, type ManifestRow } from "./manifestCells";
import { queryKeys } from "../../api/keys";
import type { RelationshipSpec, ResourceDescriptor } from "./manifestTypes";

type ChildRow = ManifestRow & { id: string };

function withStringId(row: ManifestRow, idField: string): ChildRow {
  return { ...row, id: String(row[idField] ?? "") };
}

/**
 * True iff `row`'s own `parentField` value equals `parentId` — the one
 * comparison `RelationshipSpec.parent_field`'s doc authorises
 * (`manifest.py:512`). A missing/null field on the child row never matches
 * — it is treated as "not this parent's child", not as a wildcard.
 */
export function matchesRelationshipParent(
  row: ManifestRow,
  parentField: string,
  parentId: string,
): boolean {
  const value = row[parentField];
  return value !== null && value !== undefined && String(value) === parentId;
}

export interface RelationshipChildTabProps {
  productType: string;
  relationship: RelationshipSpec;
  childResource: ResourceDescriptor;
  parentId: string;
}

export function RelationshipChildTab({
  productType,
  relationship,
  childResource,
  parentId,
}: RelationshipChildTabProps) {
  const list = childResource.list;
  const fetcher = useMemo(
    () => (list ? buildManifestListFetcher(list) : async () => []),
    [list],
  );

  const { data, isLoading, error, refetch } = useProductResource<ManifestRow>({
    productType,
    kind: childResource.kind,
    queryKeyPrefix: queryKeys.consoleManifestResource(productType),
    fetcher,
  });

  if (!list) {
    return (
      <p
        className="text-slate-400 text-sm"
        data-testid={`${productType}-${childResource.kind}-no-list`}
      >
        {childResource.label} has no list endpoint in this manifest version.
      </p>
    );
  }

  const rows = (data ?? [])
    .filter((row) =>
      matchesRelationshipParent(row, relationship.parent_field, parentId),
    )
    .map((row) => withStringId(row, childResource.id_field));

  const columns: ColumnConfig<ChildRow>[] = childResource.columns.map(
    (column) => ({
      key: column.field as keyof ChildRow,
      label: column.label,
      sortable: column.sortable,
      render: (_value, row) => renderCell(column, row),
    }),
  );

  return (
    <DataTable<ChildRow>
      columns={columns}
      data={rows}
      isLoading={isLoading}
      error={error as Error | null}
      onRetry={() => void refetch()}
      emptyMessage={childResource.empty_state}
      errorTitle={childResource.error_state}
      caption={`${childResource.plural_label} for this ${parentId}`}
    />
  );
}

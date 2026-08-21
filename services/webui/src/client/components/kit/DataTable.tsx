import { useState } from "react";
import { DataTableSortHeader } from "./DataTableSortHeader";
import { DataTablePagination } from "./DataTablePagination";
import {
  DataTableEmpty,
  DataTableError,
  DataTableLoading,
  DataTableStaleNotice,
} from "./DataTableStates";
import type {
  ColumnConfig,
  DataTableProps,
  SortDirection,
} from "./dataTableTypes";

export type { ColumnConfig, DataTableProps, SortDirection };

/**
 * Generic data table with sorting, pagination, and keyboard navigation.
 * Adapts to query loading/error states via the isLoading and error props.
 * Header and pagination live in sibling modules; this file owns sort/page
 * state and the body.
 */
export function DataTable<T extends { id?: string }>({
  columns,
  data,
  isLoading = false,
  error = null,
  onRetry,
  pageSize = 25,
  caption = "Data table with sorting and pagination",
}: DataTableProps<T>) {
  const [sortColumn, setSortColumn] = useState<keyof T | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [currentPage, setCurrentPage] = useState(1);

  const handleSort = (column: keyof T) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
    setCurrentPage(1);
  };

  const displayData = [...data];

  if (sortColumn) {
    displayData.sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];

      /* istanbul ignore next -- defensive: null/undefined cells are possible in
         real API rows but the fixtures deliberately use fully-populated data */
      if (aVal == null || bVal == null) return 0;

      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDirection === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }

      /* istanbul ignore next -- defensive: reached only for cell types other
         than string/number (e.g. boolean, object); fixtures sort by string and
         number columns only */
      return 0;
    });
  }

  const startIdx = (currentPage - 1) * pageSize;
  const paginatedData = displayData.slice(startIdx, startIdx + pageSize);
  const totalPages = Math.ceil(displayData.length / pageSize);

  console.log(
    `[DataTable] Render { rows: ${paginatedData.length}, page: ${currentPage} }`,
  );

  if (isLoading) return <DataTableLoading />;

  // An error with nothing else to show — the initial load itself failed, or
  // a refetch failed with no prior successful data to fall back to — takes
  // over the whole surface: there is no good data underneath it to protect.
  // An error while GOOD data is still present (a background refetch, e.g.
  // window refocus, failing while the last successful rows are still on
  // screen) does NOT reach this branch: replacing usable rows with a
  // full-page failure on every transient blip is the same "flapping" harm a
  // naive query-error banner would cause, just implemented as a table swap
  // instead of a toast. See DataTableStaleNotice below for that case, and
  // `components/kit/__tests__/DataTable.test.tsx` for the injection proof
  // that this precedence — error-with-no-data before empty — is real.
  if (error && data.length === 0) {
    return <DataTableError error={error} onRetry={onRetry} />;
  }

  if (paginatedData.length === 0) return <DataTableEmpty />;

  return (
    <div data-testid="datatable" className="w-full">
      {error && <DataTableStaleNotice error={error} onRetry={onRetry} />}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full border-collapse" aria-label={caption}>
          <DataTableSortHeader
            columns={columns}
            sortColumn={sortColumn}
            sortDirection={sortDirection}
            onSort={handleSort}
          />
          <tbody>
            {paginatedData.map((row, idx) => (
              <tr
                key={row.id || idx}
                data-testid="datatable-row"
                className="border-b border-slate-700 hover:bg-slate-700/50 transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={String(col.key)}
                    className="px-4 py-3 text-slate-200"
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : String(row[col.key] ?? "-")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <DataTablePagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={setCurrentPage}
      />
    </div>
  );
}

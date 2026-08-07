/**
 * Sortable header row for DataTable.
 *
 * Split out of DataTable to keep every kit file under the 5,000-character
 * house limit. Each sortable column is a real <button> so it is reachable by
 * keyboard, and aria-sort on the <th> reports current state to screen readers.
 */
import React from "react";
import { ChevronUp, ChevronDown } from "lucide-react";
import type { ColumnConfig, SortDirection } from "./dataTableTypes";

export interface DataTableSortHeaderProps<T> {
  columns: ColumnConfig<T>[];
  sortColumn: keyof T | null;
  sortDirection: SortDirection;
  onSort: (column: keyof T) => void;
}

export function DataTableSortHeader<T>({
  columns,
  sortColumn,
  sortDirection,
  onSort,
}: DataTableSortHeaderProps<T>) {
  const handleKeyDown = (e: React.KeyboardEvent, callback: () => void) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      callback();
    }
  };

  return (
    <thead>
      <tr className="bg-slate-800 border-b border-slate-700">
        {columns.map((col) => (
          <th
            key={String(col.key)}
            className="px-4 py-3 text-left text-brand font-semibold"
            role="columnheader"
            aria-sort={
              sortColumn === col.key
                ? sortDirection === "asc"
                  ? "ascending"
                  : "descending"
                : "none"
            }
          >
            {col.sortable !== false ? (
              <button
                onClick={() => onSort(col.key)}
                onKeyDown={(e) => handleKeyDown(e, () => onSort(col.key))}
                className="flex items-center gap-2 cursor-pointer hover:text-amber-300 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 px-1 py-1 rounded"
                aria-label={`Sort by ${col.label}, current: ${
                  sortColumn === col.key ? sortDirection : "unsorted"
                }`}
                data-testid={`sort-${String(col.key)}`}
              >
                <span>{col.label}</span>
                {sortColumn === col.key &&
                  (sortDirection === "asc" ? (
                    <ChevronUp size={16} />
                  ) : (
                    <ChevronDown size={16} />
                  ))}
              </button>
            ) : (
              <span>{col.label}</span>
            )}
          </th>
        ))}
      </tr>
    </thead>
  );
}

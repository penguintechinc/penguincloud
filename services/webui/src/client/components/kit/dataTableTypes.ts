/**
 * Shared types for the DataTable family.
 *
 * These live in their own module so DataTable, DataTableSortHeader, and
 * DataTablePagination can all import them without a circular dependency
 * between the parent table and its sibling parts.
 */
import type React from "react";

/** Sort direction for a sortable column. */
export type SortDirection = "asc" | "desc";

/** Declares how one column is labelled, sorted, and rendered. */
export interface ColumnConfig<T> {
  key: keyof T;
  label: string;
  /** Sortable unless explicitly false. */
  sortable?: boolean;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

export interface DataTableProps<T extends { id?: string }> {
  columns: ColumnConfig<T>[];
  data: T[];
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  pageSize?: number;
  caption?: string;
}

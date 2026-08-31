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
  /**
   * Overrides `DataTableEmpty`'s generic "No data available" copy.
   * Optional and additive — every existing caller keeps today's copy.
   * Added for the manifest-driven renderer, which must honour a resource's
   * own `empty_state` text rather than a generic fallback.
   */
  emptyMessage?: string;
  /**
   * Overrides `DataTableError`'s generic "Error loading data" heading. The
   * detail line underneath (`describeQueryError(error)`) is unaffected —
   * this only replaces the headline, same reasoning as `emptyMessage`.
   */
  errorTitle?: string;
}

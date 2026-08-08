/**
 * Component Kit v1
 * Shared, tested UI components for PenguinCloud portal.
 * All components support dark theme with theme tokens,
 * keyboard navigation, ARIA labels, and data-testid for testing.
 */

export { default as StatusBadge } from "./StatusBadge";
export { DataTable, type ColumnConfig, type DataTableProps } from "./DataTable";
export {
  DataTablePagination,
  type DataTablePaginationProps,
} from "./DataTablePagination";
export {
  DataTableSortHeader,
  type DataTableSortHeaderProps,
} from "./DataTableSortHeader";
export { EmptyState, type EmptyStateProps } from "./EmptyState";
export { ConfirmDialog, type ConfirmDialogProps } from "./ConfirmDialog";
export {
  DetailDrawer,
  type DetailDrawerProps,
  type DetailDrawerTab,
} from "./DetailDrawer";

// Note: Breadcrumbs, TenantScopeSwitcher, and ActingAsBanner are exported from their own files
// directly, not through this barrel, since they have router/store dependencies
// that make them unsuitable for all kit consumers.

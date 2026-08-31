/**
 * Component Kit v1
 * Shared, tested UI components for PenguinCloud portal.
 * All components support dark theme with theme tokens,
 * keyboard navigation, ARIA labels, and data-testid for testing.
 */

export { default as StatusBadge } from "./StatusBadge";
export { default as MutationErrorBanner } from "./MutationErrorBanner";
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
export { ActionButton } from "./ActionButton";
export { FactList, type Fact } from "./FactList";
export { RowOpenButtons } from "./RowOpenButtons";
export { ProductScreen, type ProductScreenProps } from "./ProductScreen";
export {
  useActiveTenantId,
  useProductConnection,
  useProductResource,
  type ProductConnectionState,
  type UseProductResourceOptions,
  type UseProductResourceResult,
} from "./useProductResource";
export { OperationsPanel, type OperationsPanelProps } from "./OperationsPanel";
export type {
  OperationLike,
  OperationLogLine,
  OperationsPanelSpec,
  UseOperationLogsResult,
} from "./operationsPanelTypes";

// Phase 8 Step 3 — manifest-driven console renderer (behind
// `penguincloud.declarative_console`, runs alongside the hand-written
// product screens; see `ManifestResourceScreen.tsx`'s module doc).
export {
  ManifestResourceScreen,
  type ManifestResourceScreenProps,
} from "./ManifestResourceScreen";
export { useConsoleManifests } from "./useConsoleManifests";
export { useManifestOperations } from "./useManifestOperations";
export {
  renderCell,
  resetUnknownCellKindWarnings,
  type ManifestRow,
} from "./manifestCells";
export {
  buildManifestListFetcher,
  readManifestEnvelope,
  toProxyPath,
} from "./manifestListFetcher";
export {
  CELL_KINDS,
  isCellKind,
  findResource,
  type CellKind,
  type ConsoleManifest,
  type ConsoleManifestsResponse,
  type ProductManifestEntry,
  type ResourceDescriptor,
  type ColumnSpec,
  type CellSpec,
  type ListSpec,
} from "./manifestTypes";

// Note: Breadcrumbs, TenantScopeSwitcher, and ActingAsBanner are exported from their own files
// directly, not through this barrel, since they have router/store dependencies
// that make them unsuitable for all kit consumers.

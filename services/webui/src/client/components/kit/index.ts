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

// Phase 8 — manifest-driven console renderer (behind
// `penguincloud.declarative_console`, runs alongside the hand-written
// product screens; see `ManifestResourceScreen.tsx`'s module doc).
export {
  ManifestResourceScreen,
  type ManifestResourceScreenProps,
} from "./ManifestResourceScreen";
export {
  ManifestResourceDetail,
  type ManifestResourceDetailProps,
} from "./ManifestResourceDetail";
export {
  ManifestCreateForm,
  type ManifestCreateFormProps,
} from "./ManifestCreateForm";
export { useConsoleManifests } from "./useConsoleManifests";
export {
  useManifestOperations,
  useCancelManifestOperation,
  useManifestOperationLogs,
  nextPollInterval,
} from "./useManifestOperations";
export {
  useCreateManifestResource,
  useDeleteManifestResource,
  usePerformManifestAction,
} from "./manifestMutations";
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
export { manifestItemPathBytes, toProxyItemPath } from "./manifestItemPath";
export {
  toFieldConfig,
  applyFieldAliases,
  resetUnknownFieldTypeWarnings,
} from "./manifestFormFields";
export {
  CELL_KINDS,
  isCellKind,
  FIELD_TYPES,
  isFieldType,
  findResource,
  type CellKind,
  type FieldType,
  type ConsoleManifest,
  type ConsoleManifestsResponse,
  type ProductManifestEntry,
  type ResourceDescriptor,
  type ColumnSpec,
  type CellSpec,
  type ListSpec,
  type EnvelopeSpec,
  type ItemPathSpec,
  type SelectOption,
  type ManifestFormField,
  type FormSpec,
  type FieldAlias,
  type ActionSpec,
  type DeleteSpec,
  type OperationsSpec,
} from "./manifestTypes";

// Note: Breadcrumbs, TenantScopeSwitcher, and ActingAsBanner are exported from their own files
// directly, not through this barrel, since they have router/store dependencies
// that make them unsuitable for all kit consumers.

/**
 * Shared shapes for `OperationsPanel` and its sub-renders (`OperationsPanelParts.tsx`).
 *
 * Split into their own module so the parts file does not import from
 * `OperationsPanel.tsx` — the same reason `dataTableTypes.ts` exists
 * separately from `DataTable`/`DataTableStates`.
 *
 * `OperationLike` is structural, not a re-export of `GoughOperation` or
 * `NestOperation`: any product's operation type satisfies it by having
 * these fields, which is why neither product type needs to change to be
 * handed to this generic. Both already mirror the same backend contract —
 * `Operation` in `services/portal-api/app/adapters/base.py`.
 */

/** One long-running operation, as the typed operations API returns it. */
export interface OperationLike {
  id: string;
  kind: string;
  /** Normalised, for control flow — `pending`/`running`/`succeeded`/`failed`/`cancelled`. */
  state: string;
  /** The product's own status string, verbatim, for display. */
  status: string;
  is_terminal: boolean;
  resource_id?: string | null;
  resource_kind?: string | null;
  progress?: number | null;
  detail?: string | null;
  /** Set only in the FAILED state — the product's reason. See `describeOperationError`. */
  error?: string | null;
  result?: Record<string, unknown> | null;
}

/** One line of an operation's log stream. */
export interface OperationLogLine {
  timestamp?: string | null;
  level?: string | null;
  message: string;
}

/** Shape an injected per-row log-fetch hook must return. See `OperationsPanelSpec.showLogs`. */
export interface UseOperationLogsResult {
  data: OperationLogLine[] | undefined;
  isLoading: boolean;
  error: unknown;
}

/**
 * Display + capability descriptor for one product's operations panel.
 *
 * Serialisable by design — this is the shape a Step 3 manifest-driven
 * renderer is expected to carry as an `OperationsSpec` on a descriptor.
 * `cancelAllowed` and `showLogs` are plain booleans rather than "does the
 * caller happen to pass a callback" checks, so a manifest can express them
 * as data. `onCancel`/`useOperationLogs` on `OperationsPanelProps` stay
 * callbacks regardless — cancelling and fetching logs are an action and an
 * async fetch, which a value cannot encode.
 */
export interface OperationsPanelSpec {
  /** Section heading, e.g. "Operations" / "Operations in progress". */
  title: string;
  /** aria-label for the section and the root of every generated data-testid. */
  testIdPrefix: string;
  /** Whether a live (non-terminal) operation offers a Cancel control. */
  cancelAllowed: boolean;
  /** Whether a row offers a "Show logs" disclosure. */
  showLogs: boolean;
  /**
   * Poll interval in ms the caller's own data hook is configured with.
   * The panel itself does not poll (see `OperationsPanel.tsx`'s module
   * doc) — carried here only so the descriptor is complete for the Step 3
   * manifest socket.
   */
  pollIntervalMs: number;
}

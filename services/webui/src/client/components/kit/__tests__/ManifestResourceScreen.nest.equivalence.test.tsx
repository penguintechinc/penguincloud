/**
 * The equivalence proof for Nest, now golden: does `ManifestResourceScreen`,
 * fed the committed `adapters/nest/manifest.py` descriptors, render EXACTLY
 * the output the hand-written `DatabasesPage`/`DatabaseTabs`/
 * `DatabaseDialogs`/`NestOperationsPanel` and the standalone `BillingPage`
 * used to produce — table, create form, row actions, watch-mode operations,
 * the Snapshots relationship tab, the Health `detail_tab` extension, and
 * billing?
 *
 * Sibling to `ManifestResourceScreen.equivalence.test.tsx` (Gough) and
 * `.tobogganing.equivalence.test.tsx` — same technique (Jest's per-file
 * module registry lets this mock a DIFFERENT api module than either), same
 * assertion style (rendered TEXT/values, not DOM markup). Nest convergence
 * closed the last gap (IEC byte labels, see below) and DELETED
 * `DatabasesPage.tsx`/`DatabaseTabs.tsx`/`DatabaseDialogs.tsx`/
 * `databaseColumns.tsx`/`databaseActions.ts`/`useDatabaseMutations.ts`/
 * `useNestOperations.ts`/`NestOperationsPanel.tsx`/`NestScreen.tsx`/
 * `BillingPage.tsx`/`BillingSummary.tsx`/`useNestBilling.ts`/
 * `usageColumns.tsx` — `declarative_console` is default-on, and every value
 * this file's own side-by-side comparisons asserted equal is preserved
 * below as a hardcoded expectation instead. This file no longer imports or
 * renders the hand-written screens (they no longer exist); every string it
 * asserts against `ManifestResourceScreen`'s/`BillingPanel`'s own output is
 * the exact value the deleted hand-written screen used to produce, captured
 * at the moment both sides were last proven identical — a regression in
 * either the manifest data (`nest/manifest.py`) or the renderer changes
 * these fixtures/expectations, not silently drifts past them. Mirrors
 * Gough/Tobogganing's own Step 7 rewrite.
 *
 * The `*_RESOURCE` fixtures are hand-transcriptions of
 * `services/portal-api/app/adapters/nest/manifest.py` (this worktree cannot
 * import Python — see `manifestTypes.contract.test.ts`'s module doc for
 * why). Kept deliberately literal, field for field, including the paths
 * transcribed from `nest/routes.py`'s `tenant_path()` builder and
 * `nest/mapping.py`'s `COLLECTION_ENVELOPE_KEYS`/`CREATE_FIELD_ALIASES`.
 *
 * A REAL divergence this file originally found, since fixed: for a snapshot
 * `sizeBytes` >= 1024, the manifest's generic `bytes` cell
 * (`manifestCells.tsx`'s `formatBytes`) used to render SI-style labels
 * (`KB`/`MB`/`GB`/`TB`) for a base-1024 division, disagreeing with the
 * deleted `DatabaseTabs.tsx`'s own IEC-labelled `humanBytes()`.
 * `formatBytes` now uses IEC labels (`KiB`/`MiB`/`GiB`/`TiB`) too, so both
 * sides rendered byte-identical text for the same numeric value — preserved
 * below as a hardcoded expectation.
 */
import {
  render,
  screen,
  waitFor,
  within,
  fireEvent,
} from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ManifestResourceScreen } from "../ManifestResourceScreen";
import type {
  ActionSpec,
  ColumnSpec,
  ConsoleManifest,
  DeleteSpec,
  ExtensionSlot,
  FieldAlias,
  ManifestFormField,
  OperationsSpec,
  ResourceDescriptor,
} from "../manifestTypes";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
  isProductEnabled: (key: string) => mockIsProductEnabled(key),
  useProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

// The manifest-driven renderer's LIST path — the generic byte proxy.
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

// The manifest-driven renderer's MUTATION/operation-watch path — the
// generic typed routes `ManifestResourceDetail.tsx`/`ManifestCreateForm.tsx`/
// `useManifestOperationWatch.ts` all call directly, never a product module.
const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
const mockApiPut = jest.fn();
const mockApiDelete = jest.fn();
jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
}));

// The nest API module `BillingPanel.tsx` reads through for the two billing
// endpoints — mocked wholesale so the panel's real implementation (which
// itself calls `proxyApi`) never runs.
const nestApi = { costReport: jest.fn(), costSummary: jest.fn() };
jest.mock("../../../api/resources/nest", () => ({ nestApi }));

// The REAL production registration side effect for Nest's two extension
// slots — proves the actual wiring (`nest/manifest.py`'s declared slots
// resolving against the actually-registered components), not a synthetic
// stand-in, mirroring Tobogganing's own equivalence file.
import "../../extensions/nest/register";
import BillingPanel from "../../extensions/nest/BillingPanel";

/** Every `<th role="columnheader">` label, in DOM order. */
function headerLabels(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("columnheader")
    .map((th) => th.textContent?.trim() ?? "");
}

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "nest" }],
    isLoading: false,
  });
  mockApiGet.mockResolvedValue({ data: { operations: [] } });
});

// ---------------------------------------------------------------------------
// Nest proxy paths — transcribed from `nestPaths.ts` /
// `nest/routes.py`'s `tenant_path()`, byte-exact including `{tenant}`.
// ---------------------------------------------------------------------------

const DATABASE_PROXY_PATH = "api/v1/tenants/{tenant}/data-resources";
const SNAPSHOT_PROXY_PATH = "api/v1/tenants/{tenant}/snapshots";
const SEARCH_POOL_PROXY_PATH = "api/v1/tenants/{tenant}/search-pools";
const PROTECTION_POLICY_PROXY_PATH =
  "api/v1/tenants/{tenant}/protection-policies";

// ---------------------------------------------------------------------------
// database — transcribed from `_DATABASE`/`_DATABASE_COLUMNS`/
// `_DATABASE_FORM_FIELDS` in `adapters/nest/manifest.py`.
// ---------------------------------------------------------------------------

/** `storageClass: null` is the absent-value cell. */
const RAW_DATABASE = {
  id: "d-uuid-1",
  name: "orders-db",
  phase: "Pending",
  healthState: "Healthy",
  healthMessage: "Probe succeeded",
  healthLastCheck: "2026-09-01T00:00:00Z",
  externalProvider: "aws",
  externalEndpoint: "db.example.com:5432",
  externalRegion: "us-east-1",
  resourceType: "postgres",
  storageClass: null,
  sizeGi: 20,
  engineType: "postgres-15",
  namespace: "prod",
  origination: "managed",
  createdAt: "2026-01-01T00:00:00Z",
};

const DATABASE_COLUMNS: ColumnSpec[] = [
  {
    field: "name",
    label: "Name",
    sortable: false,
    cell: { kind: "text", styles: [], relative: false },
  },
  {
    field: "phase",
    label: "Phase",
    sortable: false,
    cell: { kind: "text", styles: [], relative: false },
    absent_as: "dash",
  },
  {
    field: "healthState",
    label: "Health",
    sortable: false,
    cell: { kind: "text", styles: [], relative: false },
    absent_as: "dash",
  },
  {
    field: "resourceType",
    label: "Type",
    sortable: false,
    cell: { kind: "text", styles: [], relative: false },
    absent_as: "dash",
  },
  {
    field: "storageClass",
    label: "Storage class",
    sortable: false,
    cell: { kind: "text", styles: [], relative: false },
    absent_as: "dash",
  },
  {
    field: "sizeGi",
    label: "Size",
    sortable: false,
    cell: { kind: "number", styles: [], relative: false, unit: "GiB" },
    absent_as: "dash",
  },
];

/** Byte-for-byte `_DATABASE_FORM_FIELDS` — the SAME field set the deleted
 * `databaseColumns.tsx`'s `databaseFields` passed to `FormModalBuilder`. */
const DATABASE_FORM_FIELDS: ManifestFormField[] = [
  {
    name: "name",
    label: "Name",
    field_type: "text",
    required: true,
    options: [],
  },
  {
    name: "resourceType",
    label: "Resource type",
    field_type: "select",
    required: true,
    default_value: "postgres",
    options: [
      { value: "postgres", label: "PostgreSQL", disabled: false },
      { value: "keyvalue", label: "Key/value", disabled: false },
      { value: "search", label: "Search", disabled: false },
      { value: "object", label: "Object store", disabled: false },
      { value: "pvc/block", label: "Block volume", disabled: false },
      { value: "pvc/file", label: "File volume", disabled: false },
      { value: "nfs", label: "NFS", disabled: false },
      { value: "iscsi", label: "iSCSI", disabled: false },
    ],
  },
  {
    name: "storageClass",
    label: "Storage class",
    field_type: "text",
    required: false,
    options: [],
  },
  {
    name: "namespace",
    label: "Namespace",
    field_type: "text",
    required: false,
    default_value: "default",
    options: [],
  },
];

/** `CREATE_FIELD_ALIASES[KIND_DATABASE]` in `nest/mapping.py`, restated. */
const DATABASE_FIELD_ALIASES: FieldAlias[] = [
  { portal_name: "resourceType", product_name: "type" },
  { portal_name: "storageClass", product_name: "class" },
];

/** Byte-exact confirm copy with the deleted `databaseActions.ts`'s own
 * `message()` strings — `introspect` had NO hand-written counterpart (that
 * file's own comment: "It stays available through the adapter"), authored
 * here from `introspect_imported_resource`'s docstring instead. */
const DATABASE_ACTIONS_SPEC: ActionSpec[] = [
  {
    verb: "snapshot",
    label: "Snapshot",
    variant: "primary",
    requires: "manage",
    confirm:
      'Take a point-in-time snapshot of "{name}". The resource stays online; the snapshot is charged as stored capacity until it is deleted.',
    starts_operations: true,
    form: null,
    enabled_when_field: null,
    enabled_when_in: [],
  },
  {
    verb: "restore",
    label: "Restore",
    variant: "danger",
    requires: "manage",
    confirm:
      'Restore "{name}" from its most recent backup. Nest restores side-by-side by default, so this provisions a NEW resource rather than overwriting this one — but it consumes capacity and takes time.',
    starts_operations: true,
    form: null,
    enabled_when_field: null,
    enabled_when_in: [],
  },
  {
    verb: "introspect",
    label: "Introspect",
    variant: "primary",
    requires: "read",
    confirm:
      'Introspect "{name}" to produce a schema report for this imported resource. This does not modify the resource.',
    starts_operations: true,
    form: null,
    enabled_when_field: null,
    enabled_when_in: [],
  },
  {
    verb: "migrate",
    label: "Migrate to managed",
    variant: "danger",
    requires: "manage",
    confirm:
      'Migrate "{name}" to Nest-managed storage. This moves the underlying data and cannot be reversed from the portal.',
    starts_operations: true,
    form: null,
    enabled_when_field: null,
    enabled_when_in: [],
  },
];

const DATABASE_DELETE: DeleteSpec = {
  confirm:
    'Deleting "{name}" destroys the resource and its data. Snapshots taken from it are not removed and remain billable.',
  requires: "manage",
};

const DATABASE_RESOURCE: ResourceDescriptor = {
  kind: "database",
  label: "Database",
  plural_label: "Databases",
  id_field: "name",
  name_field: "name",
  transport: "typed",
  columns: DATABASE_COLUMNS,
  empty_state: "No databases provisioned yet.",
  error_state: "Unable to load databases.",
  list: {
    path_bytes: `/${DATABASE_PROXY_PATH}`,
    envelope: { keys: ["items"] },
    pagination: "offset",
  },
  item_path: { prefix: `/${DATABASE_PROXY_PATH}`, sample_id: "sample-db" },
  detail: { tabs: ["Overview", "Health", "Snapshots"] },
  actions: DATABASE_ACTIONS_SPEC,
  create: {
    fields: DATABASE_FORM_FIELDS,
    submit_label: "Create",
    field_aliases: DATABASE_FIELD_ALIASES,
  },
  edit: null,
  delete: DATABASE_DELETE,
  relationships: [{ child_kind: "snapshot", parent_field: "sourcePVC" }],
};

// ---------------------------------------------------------------------------
// search_pool / snapshot / protection_policy — net-new manifest surface, no
// hand-written screen anywhere in `pages/products/nest/` to compare against
// (transcribed from `_SEARCH_POOL_COLUMNS`/`_SNAPSHOT_COLUMNS`/
// `_PROTECTION_POLICY_COLUMNS`).
// ---------------------------------------------------------------------------

const SEARCH_POOL_RESOURCE: ResourceDescriptor = {
  kind: "search_pool",
  label: "Search Pool",
  plural_label: "Search Pools",
  id_field: "name",
  name_field: "name",
  transport: "proxy",
  columns: [
    {
      field: "name",
      label: "Name",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "phase",
      label: "Phase",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "endpoint",
      label: "Endpoint",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "tenantCount",
      label: "Tenants",
      sortable: false,
      cell: { kind: "number", styles: [], relative: false },
      absent_as: "zero",
    },
    {
      field: "replicas",
      label: "Replicas",
      sortable: false,
      cell: { kind: "number", styles: [], relative: false },
      absent_as: "zero",
    },
    {
      field: "version",
      label: "Version",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No search pools defined yet.",
  error_state: "Unable to load search pools.",
  list: {
    path_bytes: `/${SEARCH_POOL_PROXY_PATH}`,
    envelope: { keys: ["searchPools"] },
    pagination: "none",
  },
  item_path: { prefix: `/${SEARCH_POOL_PROXY_PATH}`, sample_id: "sample-pool" },
  detail: { tabs: [] },
  actions: [],
  create: null,
  edit: null,
  delete: null,
  relationships: [],
};

const SNAPSHOT_RESOURCE: ResourceDescriptor = {
  kind: "snapshot",
  label: "Snapshot",
  plural_label: "Snapshots",
  id_field: "name",
  name_field: "name",
  transport: "proxy",
  columns: [
    {
      field: "name",
      label: "Name",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "readyToUse",
      label: "Ready",
      sortable: false,
      cell: {
        kind: "boolean",
        styles: [],
        relative: false,
        labels: { true_label: "ready", false_label: "pending" },
      },
      absent_as: "dash",
    },
    {
      field: "sizeBytes",
      label: "Size",
      sortable: false,
      cell: { kind: "bytes", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "creationTime",
      label: "Created",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No snapshots taken yet.",
  error_state: "Unable to load snapshots.",
  list: {
    path_bytes: `/${SNAPSHOT_PROXY_PATH}`,
    envelope: { keys: ["snapshots"] },
    pagination: "none",
  },
  // No item GET route — see the manifest's own module docstring.
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  edit: null,
  delete: null,
  relationships: [],
};

const PROTECTION_POLICY_RESOURCE: ResourceDescriptor = {
  kind: "protection_policy",
  label: "Protection Policy",
  plural_label: "Protection Policies",
  id_field: "name",
  name_field: "name",
  transport: "proxy",
  columns: [
    {
      field: "name",
      label: "Name",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "snapshotSchedule",
      label: "Snapshot schedule",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "backupSchedule",
      label: "Backup schedule",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "destination",
      label: "Destination",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "lastSnapshot",
      label: "Last snapshot",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "lastBackup",
      label: "Last backup",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No protection policies defined yet.",
  error_state: "Unable to load protection policies.",
  list: {
    path_bytes: `/${PROTECTION_POLICY_PROXY_PATH}`,
    envelope: { keys: ["policies"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  edit: null,
  delete: null,
  relationships: [],
};

const NEST_OPERATIONS_SPEC: OperationsSpec = {
  label: "Operations",
  poll_interval_seconds: 5,
  cancel_allowed: false,
  show_logs: false,
  mode: "watch",
  operation_kind: "operation",
};

/** The two `ExtensionSlot`s `NEST_MANIFEST.extensions` declares. */
const NEST_MANIFEST: ConsoleManifest = {
  manifest_version: 2,
  product_type: "nest",
  display_name: "Nest",
  nav: { items: [{ kind: "database", label: "Databases" }] },
  resources: [
    DATABASE_RESOURCE,
    SEARCH_POOL_RESOURCE,
    SNAPSHOT_RESOURCE,
    PROTECTION_POLICY_RESOURCE,
  ],
  operations: NEST_OPERATIONS_SPEC,
  metrics: null,
  extensions: [
    {
      slot: "page",
      id: "billing",
      label: "Billing",
      resource: null,
      position: 0,
    },
    {
      slot: "detail_tab",
      id: "health",
      label: "Health",
      resource: "database",
      position: 0,
    },
  ],
};

function renderDatabases() {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="nest"
        productLabel="Nest"
        manifest={NEST_MANIFEST}
        resource={DATABASE_RESOURCE}
      />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// database — list columns
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen — database (golden: matches the deleted DatabasesPage's own output) — list columns", () => {
  beforeEach(() => {
    mockProxyRequest.mockImplementation(
      (_productId: number, _method: string, path: string) => {
        if (path === DATABASE_PROXY_PATH) {
          // `envelope.keys` for `database` is the BARE single key `["items"]`
          // (`COLLECTION_ENVELOPE_KEYS[KIND_DATABASE] == "items"`,
          // `nest/mapping.py`) — the raw proxy body itself, no `data`
          // wrapper, unlike Gough's `("data", "nodes")` two-level envelope.
          return Promise.resolve({ status: "success", items: [RAW_DATABASE] });
        }
        if (path === SNAPSHOT_PROXY_PATH) {
          return Promise.resolve({ status: "success", snapshots: [] });
        }
        return Promise.resolve({ status: "success" });
      },
    );
  });

  it("proxies the exact path the manifest pins", async () => {
    renderDatabases();
    await waitFor(() =>
      expect(mockProxyRequest).toHaveBeenCalledWith(
        7,
        "GET",
        DATABASE_PROXY_PATH,
      ),
    );
  });

  it("renders the same table the deleted DatabasesPage produced: same headers, same row, including the absent cell", async () => {
    const manifestScreen = renderDatabases();
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Phase",
      "Health",
      "Type",
      "Storage class",
      "Size",
    ]);

    for (const shared of [
      "orders-db",
      "Pending",
      "Healthy",
      "postgres",
      "20 GiB",
    ]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `storageClass: null` -> a dash, not blank — matching DatabasesPage's
    // own absent-value convention.
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// database — create form (field parity + resourceType/storageClass aliasing)
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen — database (golden) — create form", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      items: [RAW_DATABASE],
    });
  });

  it("renders the same field set and select options the deleted databaseFields did", async () => {
    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("nest-manifest-database-create"));
    for (const label of [
      /^Name\*$/,
      /^Resource type/,
      "Storage class",
      "Namespace",
    ]) {
      expect(
        within(manifestScreen.container).getByLabelText(label),
      ).toBeInTheDocument();
    }
    for (const option of [
      "PostgreSQL",
      "Key/value",
      "Search",
      "Object store",
      "Block volume",
      "File volume",
      "NFS",
      "iSCSI",
    ]) {
      expect(
        within(manifestScreen.container).getByText(option),
      ).toBeInTheDocument();
    }
    expect(
      within(manifestScreen.container).getByRole("button", { name: "Create" }),
    ).toBeInTheDocument();
  });

  it("posts the ALIASED type/class field names — CREATE_FIELD_ALIASES exercised client-side, matching what the deleted hand-written path's raw resourceType/storageClass names were translated to server-side", async () => {
    mockApiPost.mockResolvedValue({ data: { operation_id: null } });

    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("nest-manifest-database-create"));
    fireEvent.change(
      within(manifestScreen.container).getByLabelText(/^Name\*$/),
      {
        target: { value: "new-db" },
      },
    );
    fireEvent.change(
      within(manifestScreen.container).getByLabelText("Storage class"),
      {
        target: { value: "fast-ssd" },
      },
    );
    fireEvent.click(
      within(manifestScreen.container).getByRole("button", { name: "Create" }),
    );

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        "/products/7/resources/database",
        {
          name: "new-db",
          type: "postgres",
          class: "fast-ssd",
          namespace: "default",
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// database — row actions (snapshot/restore/migrate parity; introspect is
// manifest-only)
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen — database (golden) — row actions", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      items: [RAW_DATABASE],
    });
  });

  const SHARED_ACTIONS: Array<{
    verb: string;
    label: string;
    isDangerous: boolean;
    confirm: string;
  }> = [
    {
      verb: "snapshot",
      label: "Snapshot",
      isDangerous: false,
      confirm:
        'Take a point-in-time snapshot of "orders-db". The resource stays online; the snapshot is charged as stored capacity until it is deleted.',
    },
    {
      verb: "restore",
      label: "Restore",
      isDangerous: true,
      confirm:
        'Restore "orders-db" from its most recent backup. Nest restores side-by-side by default, so this provisions a NEW resource rather than overwriting this one — but it consumes capacity and takes time.',
    },
    {
      verb: "migrate",
      label: "Migrate to managed",
      isDangerous: true,
      confirm:
        'Migrate "orders-db" to Nest-managed storage. This moves the underlying data and cannot be reversed from the portal.',
    },
  ];

  it.each(SHARED_ACTIONS)(
    "renders the SAME $verb label and byte-identical confirm text the deleted screen used, with matching danger styling",
    async ({ verb, label, isDangerous, confirm }) => {
      const manifestScreen = renderDatabases();
      await within(manifestScreen.container).findByTestId("datatable-row");

      fireEvent.click(
        screen.getByTestId("nest-manifest-database-open-orders-db"),
      );

      expect(
        within(manifestScreen.container).getByText(label, {
          selector: "button",
        }),
      ).toBeInTheDocument();

      fireEvent.click(
        screen.getByTestId(`nest-manifest-database-action-${verb}`),
      );

      expect(
        within(
          screen.getByTestId("nest-manifest-database-action-confirm"),
        ).getByText(confirm),
      ).toBeInTheDocument();

      // Danger variant surfaces as ConfirmDialog's AlertTriangle icon — a
      // behavioural signal, not a CSS-class inspection.
      const manifestHasIcon =
        screen
          .getByTestId("nest-manifest-database-action-confirm")
          .querySelector("svg") !== null;
      expect(manifestHasIcon).toBe(isDangerous);
    },
  );

  it("confirming Restore dispatches through the SAME typed action route the deleted screen's own mutation ultimately called, keyed by name", async () => {
    mockApiPost.mockResolvedValue({ data: { operations: [] } });

    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(
      screen.getByTestId("nest-manifest-database-open-orders-db"),
    );
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-action-restore"),
    );
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-action-confirm-confirm"),
    );
    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        "/products/7/resources/database/orders-db/actions/restore",
        {},
      ),
    );
  });

  it("introspect: manifest-only (no hand-written button ever existed — the deleted databaseActions.ts's own comment: 'It stays available through the adapter'); renders the manifest's own authored copy, non-dangerous, requires read", async () => {
    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-open-orders-db"),
    );

    expect(
      within(manifestScreen.container).getByText("Introspect", {
        selector: "button",
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-action-introspect"),
    );

    expect(
      within(
        screen.getByTestId("nest-manifest-database-action-confirm"),
      ).getByText(
        'Introspect "orders-db" to produce a schema report for this imported resource. This does not modify the resource.',
      ),
    ).toBeInTheDocument();
    // Non-dangerous -> no AlertTriangle.
    expect(
      screen
        .getByTestId("nest-manifest-database-action-confirm")
        .querySelector("svg"),
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// database — watch-mode operations (OperationsSpec.mode="watch",
// operation_kind="operation" overriding the resource's own "database" kind)
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen — database (golden) — watch-mode operations", () => {
  const RAW_OPERATION = {
    id: "op-1",
    kind: "operation",
    state: "running",
    status: "Provisioning",
    is_terminal: false,
    resource_id: "orders-db",
    resource_kind: "database",
    progress: null,
    detail: "snapshot",
    error: null,
    result: null,
  };

  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      items: [RAW_DATABASE],
    });
  });

  it('mode="watch" polls GET /operations/operation/{id} — operation_kind overrides the watched resource\'s own "database" kind, matching the deleted useNestOperations.ts\'s own behaviour', async () => {
    mockApiPost.mockResolvedValue({ data: { operations: [{ id: "op-1" }] } });
    mockApiGet.mockImplementation((url: string) =>
      url === "/products/7/operations/operation/op-1"
        ? Promise.resolve({ data: RAW_OPERATION })
        : Promise.resolve({ data: { operations: [] } }),
    );

    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-open-orders-db"),
    );
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-action-snapshot"),
    );
    fireEvent.click(
      screen.getByTestId("nest-manifest-database-action-confirm-confirm"),
    );

    // The load-bearing assertion: NOT `/operations/database/op-1` (the
    // resource's own kind), which is what a manifest omitting
    // `operation_kind` would address and which `NestAdapter.get_operation`
    // 501s against.
    await waitFor(() =>
      expect(mockApiGet).toHaveBeenCalledWith(
        "/products/7/operations/operation/op-1",
      ),
    );
    expect(
      await within(manifestScreen.container).findByTestId(
        "nest-manifest-database-operation-op-1",
      ),
    ).toBeInTheDocument();
    expect(
      within(manifestScreen.container).getByText("operation"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// database — Snapshots relationship tab (RelationshipSpec, parent_field
// "sourcePVC") vs the deleted DatabaseTabs.tsx's hand-filtered SnapshotsTab
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen's Snapshots tab (golden: matches the deleted DatabaseTabs.tsx's hand-filtered SnapshotsTab)", () => {
  // `sizeBytes: 2048` is deliberate — see this file's module doc. Chosen
  // >= 1024 specifically so the byte-format equivalence is exercised, not
  // dodged.
  const SNAPSHOT_MINE = {
    name: "orders-db-snap-1",
    sourcePVC: "orders-db",
    readyToUse: true,
    sizeBytes: 2048,
    creationTime: "2026-02-01T00:00:00Z",
  };
  const SNAPSHOT_OTHER = {
    name: "billing-db-snap-1",
    sourcePVC: "billing-db",
    readyToUse: false,
    sizeBytes: 512,
    creationTime: "2026-02-02T00:00:00Z",
  };

  beforeEach(() => {
    mockProxyRequest.mockImplementation(
      (_productId: number, _method: string, path: string) => {
        if (path === DATABASE_PROXY_PATH) {
          return Promise.resolve({ status: "success", items: [RAW_DATABASE] });
        }
        if (path === SNAPSHOT_PROXY_PATH) {
          return Promise.resolve({
            status: "success",
            snapshots: [SNAPSHOT_MINE, SNAPSHOT_OTHER],
          });
        }
        return Promise.resolve({ status: "success" });
      },
    );
  });

  it("lists only the parent's own snapshots, matching sourcePVC===database.name — and renders the byte-unit format the deleted hand-written tab's own IEC humanBytes() produced", async () => {
    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(
      screen.getByTestId("nest-manifest-database-open-orders-db"),
    );
    fireEvent.click(
      within(screen.getByTestId("nest-manifest-database-drawer")).getByTestId(
        "nest-manifest-database-drawer-tab-rel-snapshot",
      ),
    );
    const manifestPanel = screen.getByTestId(
      "nest-manifest-database-drawer-panel",
    );
    const manifestRows =
      await within(manifestPanel).findAllByTestId("datatable-row");
    expect(manifestRows).toHaveLength(1);
    expect(
      within(manifestPanel).getByText("orders-db-snap-1"),
    ).toBeInTheDocument();
    expect(
      within(manifestPanel).queryByText("billing-db-snap-1"),
    ).not.toBeInTheDocument();
    expect(within(manifestPanel).getByText("ready")).toBeInTheDocument();

    // The SAME 2048-byte value renders as "2.0 KiB" — the deleted
    // DatabaseTabs.tsx's own IEC `humanBytes()`'s output, now produced by
    // the manifest's generic `bytes` cell (`manifestCells.tsx`'s
    // `formatBytes`, IEC-labelled). Asserted as equality, not a substring.
    expect(within(manifestPanel).getByText("2.0 KiB")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// database — Health detail_tab extension slot (golden: matches the deleted
// DatabaseTabs.tsx's hand-written Health tab)
// ---------------------------------------------------------------------------

describe("ManifestResourceScreen's Health detail_tab slot (golden: matches the deleted DatabaseTabs.tsx's hand-written Health tab)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      items: [RAW_DATABASE],
    });
  });

  it("renders the SAME six health facts the deleted hand-written tab did, through the REAL registered DatabaseHealthTab extension (components/extensions/nest/register.ts)", async () => {
    const manifestScreen = renderDatabases();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(
      screen.getByTestId("nest-manifest-database-open-orders-db"),
    );
    fireEvent.click(
      within(screen.getByTestId("nest-manifest-database-drawer")).getByTestId(
        "nest-manifest-database-drawer-tab-ext-health",
      ),
    );
    // Lazily loaded through React.lazy/Suspense (ExtensionDetailTabSlot) —
    // awaited, matching the standalone `DatabaseHealthTab.test.tsx`'s own
    // synchronous render but through the REAL slot resolution this time.
    const manifestFacts = await within(
      screen.getByTestId("nest-manifest-database-drawer"),
    ).findByTestId("nest-health-facts");

    for (const shared of [
      "Healthy",
      "Probe succeeded",
      "2026-09-01T00:00:00Z",
      "aws",
      "db.example.com:5432",
      "us-east-1",
    ]) {
      expect(within(manifestFacts).getByText(shared)).toBeInTheDocument();
    }
  });
});

// ---------------------------------------------------------------------------
// billing — BillingPanel (page ExtensionSlot), golden: matches the deleted
// standalone BillingPage's own output
// ---------------------------------------------------------------------------

describe("BillingPanel — Nest billing (golden: matches the deleted BillingPage's own output)", () => {
  const BILLING_SLOT: ExtensionSlot = {
    slot: "page",
    id: "billing",
    label: "Billing",
    resource: null,
    position: 0,
  };
  const RECORDS = [
    {
      month: "2026-07",
      totalTokens: 1250,
      totalCostUsd: 42.5,
      breakdown: { postgres: 1000, object: 250 },
      updatedAt: "2026-08-01T00:00:00Z",
    },
  ];

  function renderBilling() {
    return render(
      <QueryClientProvider client={createAppQueryClient()}>
        <BillingPanel
          productType="nest"
          productId={7}
          tenantId={42}
          slot={BILLING_SLOT}
        />
      </QueryClientProvider>,
    );
  }

  beforeEach(() => {
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: { records: RECORDS },
    });
    nestApi.costSummary.mockResolvedValue({
      available: true,
      data: { totalTokens: 1250, totalCostUsd: 42.5, months: 1 },
    });
  });

  it("renders the usage table and summary tiles the deleted BillingPage produced, from the SAME two endpoints", async () => {
    const panel = renderBilling();

    // Scoped to the table specifically — "42.50" also appears in the
    // summary tile below, so an unscoped query is ambiguous the moment both
    // are on screen (BillingPanel.test.tsx's own precedent).
    const panelTable = within(
      await within(panel.container).findByRole("table"),
    );

    for (const shared of ["2026-07", "42.50", "1,250"]) {
      expect(panelTable.getByText(shared)).toBeInTheDocument();
    }

    const panelSummary = within(
      await within(panel.container).findByTestId("nest-billing-summary"),
    );
    expect(panelSummary.getByText("42.50")).toBeInTheDocument();
    expect(panelSummary.getByText("1")).toBeInTheDocument();
  });

  it("breaks usage down per resource type, matching the deleted UsageBreakdown's own output", async () => {
    const panel = renderBilling();
    const panelBreakdown = await within(panel.container).findByTestId(
      "nest-usage-breakdown-2026-07",
    );
    for (const shared of ["postgres", "object"]) {
      expect(within(panelBreakdown).getByText(shared)).toBeInTheDocument();
    }
  });

  it("says the cost service is absent rather than an empty table, on the SAME tri-state condition the deleted screen used", async () => {
    nestApi.costReport.mockResolvedValue({ available: false, data: null });
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    const panel = renderBilling();

    expect(
      await within(panel.container).findByTestId("nest-billing-unavailable"),
    ).toBeInTheDocument();
    expect(
      within(panel.container).queryByTestId("nest-billing-summary"),
    ).toBeNull();
  });

  it("distinguishes a metered tenant with zero months from an absent service", async () => {
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: { records: [] },
    });

    const panel = renderBilling();
    await waitFor(() => {
      expect(
        within(panel.container).queryByTestId("nest-billing-unavailable"),
      ).not.toBeInTheDocument();
    });
    expect(
      within(panel.container).queryByTestId("nest-usage-breakdown"),
    ).toBeNull();
  });

  it("dashes an absent aggregate figure rather than rendering a false zero", async () => {
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    const panel = renderBilling();
    expect(
      await within(panel.container).findByTestId("nest-billing-summary-absent"),
    ).toBeInTheDocument();
    expect(within(panel.container).queryByText("0.00")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// search_pool / snapshot / protection_policy — net-new manifest surface, no
// hand-written screen anywhere to compare against; a light "renders headers
// without error" smoke check is the whole ask.
// ---------------------------------------------------------------------------

describe("search_pool / snapshot / protection_policy — net-new manifest surface", () => {
  it("search_pool renders its declared headers without error", async () => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      searchPools: [
        {
          name: "pool-a",
          phase: "Ready",
          endpoint: "pool-a.internal:9200",
          tenantCount: 3,
          replicas: 2,
          version: "8.1",
        },
      ],
    });
    const screenEl = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="nest"
          productLabel="Nest"
          manifest={NEST_MANIFEST}
          resource={SEARCH_POOL_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await within(screenEl.container).findByTestId("datatable-row");
    expect(headerLabels(screenEl.container)).toEqual([
      "Name",
      "Phase",
      "Endpoint",
      "Tenants",
      "Replicas",
      "Version",
    ]);
  });

  it("snapshot renders its declared headers without error (item_path=null — no drawer)", async () => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      snapshots: [
        {
          name: "snap-a",
          readyToUse: true,
          sizeBytes: 512,
          creationTime: "2026-01-01T00:00:00Z",
        },
      ],
    });
    const screenEl = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="nest"
          productLabel="Nest"
          manifest={NEST_MANIFEST}
          resource={SNAPSHOT_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await within(screenEl.container).findByTestId("datatable-row");
    expect(headerLabels(screenEl.container)).toEqual([
      "Name",
      "Ready",
      "Size",
      "Created",
    ]);
  });

  it("protection_policy renders its declared headers without error (item_path=null)", async () => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      policies: [
        {
          name: "pol-a",
          snapshotSchedule: "0 * * * *",
          backupSchedule: null,
          destination: "s3://bucket",
          lastSnapshot: null,
          lastBackup: null,
        },
      ],
    });
    const screenEl = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="nest"
          productLabel="Nest"
          manifest={NEST_MANIFEST}
          resource={PROTECTION_POLICY_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await within(screenEl.container).findByTestId("datatable-row");
    expect(headerLabels(screenEl.container)).toEqual([
      "Name",
      "Snapshot schedule",
      "Backup schedule",
      "Destination",
      "Last snapshot",
      "Last backup",
    ]);
  });
});

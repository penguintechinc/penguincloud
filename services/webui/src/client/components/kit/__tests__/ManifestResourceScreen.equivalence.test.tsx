/**
 * The equivalence proof: does `ManifestResourceScreen`, fed Gough's
 * committed `ResourceDescriptor`s, reproduce every hand-written screen's
 * rendered table exactly?
 *
 * Phase 8 Step 3 left this FALSIFIED on purpose: the committed manifest's
 * `nodes` columns (id, name, state, posture, ipv4, created_at) were not the
 * set `nodeColumns.tsx` actually renders (name, state, posture, ipv4,
 * hardware_tags) — a content gap in the Step 3 Python authoring, not a
 * renderer defect. Step 8 closed that gap in `gough/manifest.py` (see that
 * module's own column-block comments for exactly what changed and why), and
 * this file is rewritten from asserting the gap to asserting it is gone —
 * headers AND a sample row's cells, including an absent-value cell,
 * identical between the manifest-driven render and the hand-written one.
 *
 * Phase 8 Step 5 frontend widens this file's scope past the table. The
 * `*_RESOURCE` fixtures below now carry Gough's REAL `item_path`/`actions`/
 * `create`/`edit`/`operations` — the "simplified to the empty/null case"
 * `actions`/`create`/`item_path` schema-v1-era fixtures are gone — so this
 * file now also proves:
 *
 * - the operations panel (list/poll spec/cancel/logs) on all three screens;
 * - row actions, `{name}` confirm interpolation, and danger-variant styling
 *   on nodes (and, where the manifest's OWN content actually matches — see
 *   the agents block below — on agents too);
 * - the biomes create AND edit forms;
 * - the agents `hostname` column's `fallback_fields` chain.
 *
 * The `*_RESOURCE` fixtures are still hand-transcriptions of
 * `services/portal-api/app/adapters/gough/manifest.py` (this worktree
 * cannot import Python — see `manifestTypes.contract.test.ts`'s module doc
 * for why cross-language checks in this repo read source as text instead).
 * Kept deliberately literal, field for field.
 *
 * One REAL divergence this file found and does NOT paper over: Gough's own
 * `agents` manifest declares `suspend`'s `confirm` as `"Suspend this
 * agent?"` and `resume` with NO `confirm` at all, while `AgentsPage.tsx`
 * hand-writes `"Suspending stops this agent from acting until it is
 * resumed."` / `"Resuming returns this agent to service."` — neither
 * matches. The agents actions block below asserts what is actually TRUE on
 * each side rather than a false equality; see that block's own comment.
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
import { ProductResourceRoute } from "../ProductResourceRoute";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

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

// The hand-written pages read through `goughApi`.
const goughApi = {
  listNodes: jest.fn(),
  listBiomes: jest.fn(),
  listAgents: jest.fn(),
};
jest.mock("../../../api/resources/gough", () => ({ goughApi }));

// Both the hand-written pages (operations/actions) AND the manifest-driven
// panel's own `listOperations`/`performAction` fixtures below read through
// this — the hand-written side directly (`goughOperationsApi.*`), the
// manifest side only for `listOperations`' SHAPE, since `ManifestResourceScreen`
// reads operations through the generic typed route (`lib/api`, mocked
// below), never through this Gough-specific module.
const goughOperationsApi = {
  listOperations: jest.fn(),
  performAction: jest.fn(),
};
jest.mock("../../../api/resources/goughOperations", () => ({
  goughOperationsApi,
}));

// The manifest-driven renderer reads through the generic byte proxy for
// LIST data...
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

// ...and through the generic typed portal routes (operations/actions/
// create/edit/delete) for everything mutating — `ManifestResourceDetail.tsx`
// /`ManifestCreateForm.tsx`/`useManifestOperations.ts` all call `lib/api`
// directly, never `api/resources/gough`.
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

// Imported after the mocks above are set up — an `import` at the top of the
// file would require the pages (and their transitive `goughOperationsApi`
// mock factory) before the `const`s those factories close over are
// assigned, the same ordering `GoughScreens.test.tsx` already follows.
import NodesPage from "../../../pages/products/gough/NodesPage";
import BiomesPage from "../../../pages/products/gough/BiomesPage";
import AgentsPage from "../../../pages/products/gough/AgentsPage";

/** Every `<th role="columnheader">` label, in DOM order. */
function headerLabels(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("columnheader")
    .map((th) => th.textContent?.trim() ?? "");
}

/** One operation, shaped exactly as the typed operations contract returns
 * it (`OperationLike` / Gough's own `GoughOperation`) — used identically as
 * the fixture for BOTH the hand-written `goughOperationsApi.listOperations`
 * mock and the generic `lib/api` `GET .../operations` mock, so an operations
 * panel equivalence proof is comparing the SAME data through two paths. */
const RAW_OPERATION = {
  id: "op-1",
  kind: "deployment",
  state: "running",
  status: "Deploying",
  is_terminal: false,
  resource_id: "12",
  resource_kind: "nodes",
  progress: null,
  detail: null,
  error: null,
  result: null,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
  goughOperationsApi.listOperations.mockResolvedValue([]);
  // Safe default: no test relies on operations rendering unless it sets
  // this explicitly, and the panel renders NOTHING for an empty array
  // (`OperationsPanel.tsx`'s own "hidden entirely" contract) — never a
  // false "operations: []" for a test that never asked about operations.
  mockApiGet.mockResolvedValue({ data: { operations: [] } });
});

// ---------------------------------------------------------------------------
// nodes
// ---------------------------------------------------------------------------

/** One node, shaped exactly as Gough's own raw JSON — both renderers see
 * the identical row. `posture: null` is the absent-value cell. */
const RAW_NODE = {
  id: 12,
  name: "rack-a-01",
  state: "ready",
  posture: null,
  ipv4: "10.0.0.12",
  hardware_tags: ["gpu"],
  created_at: "2026-01-01T00:00:00Z",
};

/**
 * Transcribed from `_NODES_COLUMNS`/`_NODES` in `gough/manifest.py`,
 * including `item_path` and `actions` — Phase 8 Step 5 frontend closes the
 * "simplified to the empty/null case" gap the earlier fixture left.
 */
const GOUGH_NODES_RESOURCE: ResourceDescriptor = {
  kind: "nodes",
  label: "Node",
  plural_label: "Nodes",
  id_field: "id",
  name_field: "name",
  transport: "typed",
  columns: [
    {
      field: "name",
      label: "Name",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "state",
      label: "State",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "posture",
      label: "Posture",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "ipv4",
      label: "IPv4",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "hardware_tags",
      label: "Tags",
      sortable: false,
      cell: { kind: "tags", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No nodes enrolled yet.",
  error_state: "Unable to load nodes.",
  list: {
    path_bytes: "/api/v1/nodes/",
    envelope: { keys: ["data", "nodes"] },
    pagination: "cursor",
  },
  item_path: { prefix: "/api/v1/nodes", sample_id: "1" },
  detail: { tabs: ["Overview", "Tags", "Biomes"] },
  actions: [
    {
      verb: "deploy",
      label: "Deploy",
      variant: "danger",
      requires: "manage",
      confirm:
        'Deploying commissions this hardware and begins provisioning it. This affects node "{name}".',
      starts_operations: true,
      form: null,
      enabled_when_field: null,
      enabled_when_in: [],
    },
    {
      verb: "evacuate",
      label: "Evacuate",
      variant: "danger",
      requires: "manage",
      confirm:
        'Evacuating drains every workload off this node before removing it from service. This affects node "{name}".',
      starts_operations: false,
      form: null,
      enabled_when_field: null,
      enabled_when_in: [],
    },
    {
      verb: "reject",
      label: "Reject",
      variant: "danger",
      requires: "manage",
      confirm:
        'Rejecting removes this node from the fleet. It must be re-discovered to return. This affects node "{name}".',
      starts_operations: false,
      form: null,
      enabled_when_field: null,
      enabled_when_in: [],
    },
  ],
  create: null,
  edit: null,
  delete: null,
  relationships: [],
};

const GOUGH_OPERATIONS_SPEC = {
  label: "Operations",
  poll_interval_seconds: 5,
  cancel_allowed: true,
  show_logs: true,
};

const GOUGH_MANIFEST_NODES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "nodes", label: "Nodes" }] },
  resources: [GOUGH_NODES_RESOURCE],
  operations: GOUGH_OPERATIONS_SPEC,
  metrics: null,
  extensions: [],
};

function renderNodesBoth() {
  const nodesPage = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <NodesPage />
    </QueryClientProvider>,
  );
  const manifestScreen = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_NODES}
        resource={GOUGH_NODES_RESOURCE}
      />
    </QueryClientProvider>,
  );
  return { nodesPage, manifestScreen };
}

describe("ManifestResourceScreen vs NodesPage — nodes", () => {
  beforeEach(() => {
    goughApi.listNodes.mockResolvedValue([RAW_NODE]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [RAW_NODE] },
    });
  });

  it("proxies the exact path NodesPage's own goughPaths.ts pins", async () => {
    renderNodesBoth();
    await waitFor(() => expect(mockProxyRequest).toHaveBeenCalled());
    expect(mockProxyRequest).toHaveBeenCalledWith(7, "GET", "api/v1/nodes/");
  });

  it("renders an IDENTICAL table to NodesPage: same headers, same row, including the absent cell", async () => {
    const { nodesPage, manifestScreen } = renderNodesBoth();

    const nodesRow = await within(nodesPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    // Headers: same set, same order — the falsification's own gap (ID/
    // Enrolled present only on the manifest side, Tags present only on
    // NodesPage) is what this line proves closed.
    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(nodesPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "State",
      "Posture",
      "IPv4",
      "Tags",
    ]);

    // Every shared value, verbatim.
    for (const shared of ["rack-a-01", "ready", "10.0.0.12", "gpu"]) {
      expect(within(nodesRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // The absent cell (`posture: null`) renders identically — a dash, not
    // a blank, not "Unknown", on both sides.
    expect(within(nodesRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("honours the manifest's own empty_state copy, not the generic fallback", async () => {
    goughApi.listNodes.mockResolvedValue([]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [] },
    });

    const { manifestScreen } = renderNodesBoth();

    expect(
      await within(manifestScreen.container).findByText(
        "No nodes enrolled yet.",
      ),
    ).toBeInTheDocument();
  });

  it("honours the manifest's own error_state copy on a failed load", async () => {
    mockProxyRequest.mockRejectedValue(new Error("boom"));

    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="gough"
          productLabel="Gough"
          manifest={GOUGH_MANIFEST_NODES}
          resource={GOUGH_NODES_RESOURCE}
        />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("Unable to load nodes."),
    ).toBeInTheDocument();
  });

  it("renders the operations panel identically to NodesPage's own hand-written OperationsPanel: same title, same operation kind/status, cancel control and logs disclosure both present", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([RAW_OPERATION]);
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const { nodesPage, manifestScreen } = renderNodesBoth();

    for (const container of [nodesPage.container, manifestScreen.container]) {
      const panel = await within(container).findByText("Operations");
      expect(panel).toBeInTheDocument();
      expect(within(container).getByText("deployment")).toBeInTheDocument();
      // Non-terminal + cancelAllowed=true on both sides -> a Cancel control.
      expect(
        within(container).getByText("Cancel", { selector: "button" }),
      ).toBeInTheDocument();
      // showLogs=true on both sides -> the "Show logs" disclosure toggle.
      expect(within(container).getByText("Show logs")).toBeInTheDocument();
    }
  });

  it("cancelling a live operation calls the SAME portal cancel route through both panels' own mutation", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([RAW_OPERATION]);
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );
    mockApiPost.mockResolvedValue({ data: {} });

    const { manifestScreen } = renderNodesBoth();

    const cancelBtn = await within(manifestScreen.container).findByText(
      "Cancel",
      { selector: "button" },
    );
    fireEvent.click(cancelBtn);

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        "/products/7/operations/deployment/op-1/cancel",
      ),
    );
  });

  it("renders the SAME row actions (Deploy/Evacuate/Reject) and Deploy's confirm interpolates {name} byte-identical to NodesPage's own hand-written string", async () => {
    const { nodesPage, manifestScreen } = renderNodesBoth();

    await within(nodesPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-node-open-12"));
    fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

    for (const label of ["Deploy", "Evacuate", "Reject"]) {
      expect(
        within(nodesPage.container).getByText(label, { selector: "button" }),
      ).toBeInTheDocument();
      expect(
        within(manifestScreen.container).getByText(label, {
          selector: "button",
        }),
      ).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId("gough-node-action-deploy"));
    fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-deploy"));

    const expectedConfirm =
      'Deploying commissions this hardware and begins provisioning it. This affects node "rack-a-01".';
    expect(
      within(screen.getByTestId("gough-node-confirm")).getByText(
        expectedConfirm,
      ),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId("gough-manifest-nodes-action-confirm"),
      ).getByText(expectedConfirm),
    ).toBeInTheDocument();
  });

  it("confirming Deploy dispatches through the SAME typed action route both sides ultimately call", async () => {
    goughOperationsApi.performAction.mockResolvedValue({
      operation_ids: ["op-9"],
    });
    mockApiPost.mockResolvedValue({ data: { accepted: true } });

    const { manifestScreen } = renderNodesBoth();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
    fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-deploy"));
    fireEvent.click(
      screen.getByTestId("gough-manifest-nodes-action-confirm-confirm"),
    );

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        "/products/7/resources/nodes/12/actions/deploy",
        {},
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// biomes
// ---------------------------------------------------------------------------

/** `workload_type: null` is the absent-value cell for this resource. */
const RAW_BIOME = {
  id: 4,
  name: "web",
  is_active: true,
  biome_kind: "custom",
  workload_type: null,
  version: "1.2.3",
};

/** The SAME field set `create` and `edit` both use — byte-for-byte
 * `_BIOME_FORM_FIELDS` in `gough/manifest.py`, which is itself the SAME
 * array `BiomesPage.tsx` passes to `FormModalBuilder` (`biomeFields`) for
 * both "New biome" and "Edit biome". */
const BIOME_FORM_FIELDS = [
  {
    name: "name",
    label: "Name",
    field_type: "text",
    required: true,
    options: [],
  },
  {
    name: "biome_kind",
    label: "Kind",
    field_type: "select",
    required: false,
    default_value: "custom",
    options: [
      { value: "custom", label: "Custom", disabled: false },
      { value: "k8s", label: "Kubernetes", disabled: false },
      { value: "storage", label: "Storage", disabled: false },
    ],
  },
  {
    name: "workload_type",
    label: "Workload type",
    field_type: "select",
    required: false,
    default_value: "lxc",
    options: [
      { value: "lxc", label: "LXC", disabled: false },
      { value: "vm", label: "VM", disabled: false },
    ],
  },
  {
    name: "version",
    label: "Version",
    field_type: "text",
    required: false,
    options: [],
  },
];

/** Transcribed from `_BIOMES_COLUMNS`/`_BIOMES` in `gough/manifest.py`,
 * including `item_path`/`create`/`edit`/`delete`. */
const GOUGH_BIOMES_RESOURCE: ResourceDescriptor = {
  kind: "biomes",
  label: "Biome",
  plural_label: "Biomes",
  id_field: "id",
  name_field: "name",
  transport: "typed",
  columns: [
    {
      field: "name",
      label: "Name",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "is_active",
      label: "Active",
      sortable: false,
      cell: {
        kind: "boolean",
        styles: [],
        relative: false,
        labels: { true_label: "active", false_label: "inactive" },
      },
      absent_as: "dash",
    },
    {
      field: "biome_kind",
      label: "Kind",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "workload_type",
      label: "Workload",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "version",
      label: "Version",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No biomes defined yet.",
  error_state: "Unable to load biomes.",
  list: {
    path_bytes: "/api/v1/biomes/",
    envelope: { keys: ["data", "biomes"] },
    pagination: "cursor",
  },
  item_path: { prefix: "/api/v1/biomes", sample_id: "1" },
  detail: { tabs: ["Overview", "Eligibility"] },
  actions: [],
  create: {
    fields: BIOME_FORM_FIELDS,
    submit_label: "Create",
    field_aliases: [],
  },
  edit: { fields: BIOME_FORM_FIELDS, submit_label: "Save", field_aliases: [] },
  delete: {
    confirm: "Delete this biome? Nodes running it will need reassignment.",
    requires: "manage",
  },
  relationships: [],
};

const GOUGH_MANIFEST_BIOMES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "biomes", label: "Biomes" }] },
  resources: [GOUGH_BIOMES_RESOURCE],
  operations: GOUGH_OPERATIONS_SPEC,
  metrics: null,
  extensions: [],
};

function renderBiomesBoth() {
  const biomesPage = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <BiomesPage />
    </QueryClientProvider>,
  );
  const manifestScreen = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_BIOMES}
        resource={GOUGH_BIOMES_RESOURCE}
      />
    </QueryClientProvider>,
  );
  return { biomesPage, manifestScreen };
}

describe("ManifestResourceScreen vs BiomesPage — biomes", () => {
  beforeEach(() => {
    goughApi.listBiomes.mockResolvedValue([RAW_BIOME]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { biomes: [RAW_BIOME] },
    });
  });

  it("renders an IDENTICAL table to BiomesPage: same headers, same row, including the absent cell", async () => {
    const { biomesPage, manifestScreen } = renderBiomesBoth();

    const biomesRow = await within(biomesPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(biomesPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Active",
      "Kind",
      "Workload",
      "Version",
    ]);

    for (const shared of ["web", "active", "custom", "1.2.3"]) {
      expect(within(biomesRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `workload_type: null` -> a dash on both sides, not blank.
    expect(within(biomesRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("renders the operations panel identically to BiomesPage's own hand-written OperationsPanel", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([RAW_OPERATION]);
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const { biomesPage, manifestScreen } = renderBiomesBoth();

    for (const container of [biomesPage.container, manifestScreen.container]) {
      expect(
        await within(container).findByText("Operations"),
      ).toBeInTheDocument();
      expect(within(container).getByText("deployment")).toBeInTheDocument();
    }
  });

  it("renders an equivalent CREATE form: same field labels, same select options, same submit label — matching BiomesPage's biomeFields exactly", async () => {
    // The two modals are opened SEQUENTIALLY, not simultaneously: both forms
    // use `id="name"`/`id="biome_kind"`/etc, and a native `<label for="name">`
    // resolves its control via `document.getElementById` (or the `.labels`
    // DOM property) — genuinely document-wide, not scoped to a
    // `within(container)` query — so two independent forms sharing the same
    // field names open at once is an id COLLISION no query scoping can undo.
    // Sequencing them is what makes the two sides comparable, not a
    // workaround for anything either component gets wrong.
    const { biomesPage, manifestScreen } = renderBiomesBoth();
    await within(biomesPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-biome-create"));
    for (const label of [/^Name\*$/, "Kind", "Workload type", "Version"]) {
      expect(
        within(biomesPage.container).getByLabelText(label),
      ).toBeInTheDocument();
    }
    for (const option of ["Custom", "Kubernetes", "Storage", "LXC", "VM"]) {
      expect(
        within(biomesPage.container).getByText(option),
      ).toBeInTheDocument();
    }
    expect(
      within(biomesPage.container).getByRole("button", { name: "Create" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(biomesPage.container).getByRole("button", { name: "Cancel" }),
    );

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-create"));
    for (const label of [/^Name\*$/, "Kind", "Workload type", "Version"]) {
      expect(
        within(manifestScreen.container).getByLabelText(label),
      ).toBeInTheDocument();
    }
    for (const option of ["Custom", "Kubernetes", "Storage", "LXC", "VM"]) {
      expect(
        within(manifestScreen.container).getByText(option),
      ).toBeInTheDocument();
    }
    expect(
      within(manifestScreen.container).getByRole("button", { name: "Create" }),
    ).toBeInTheDocument();
  });

  it("renders an equivalent EDIT form: same field set, submit label 'Save' — and, matching BiomesPage exactly, NEVER prefilled from the selected row", async () => {
    const { biomesPage, manifestScreen } = renderBiomesBoth();
    await within(biomesPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    // BiomesPage's own edit path: open the row (RowOpenButtons, not the
    // table itself), then Edit. Sequenced (not simultaneous with the
    // manifest side) for the same id-collision reason the CREATE test above
    // documents.
    fireEvent.click(screen.getByTestId("gough-biome-open-4"));
    fireEvent.click(screen.getByTestId("gough-biome-edit"));
    const handWrittenNameInput = within(biomesPage.container).getByLabelText(
      /^Name\*$/,
    );
    // Never prefilled from the row (real biome name is "web").
    expect(handWrittenNameInput).toHaveValue("");
    expect(
      within(biomesPage.container).getByRole("button", { name: "Save" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(biomesPage.container).getByRole("button", { name: "Cancel" }),
    );

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-open-4"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-edit"));
    const manifestNameInput = await within(
      manifestScreen.container,
    ).findByLabelText(/^Name\*$/);
    expect(manifestNameInput).toHaveValue("");
    expect(
      within(manifestScreen.container).getByRole("button", { name: "Save" }),
    ).toBeInTheDocument();
  });

  it("submits the edit form's full field payload (react-libs' FormBuilder submits the whole form, not a diff) to the generic typed item route", async () => {
    mockApiPut.mockResolvedValue({ data: { id: "4" } });
    const { manifestScreen } = renderBiomesBoth();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-open-4"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-edit"));

    fireEvent.change(await screen.findByLabelText(/^Name\*$/), {
      target: { value: "web-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiPut).toHaveBeenCalledWith(
        "/products/7/resources/biomes/4",
        {
          name: "web-2",
          // Not prefilled from the row (see the test above) — these are the
          // SELECT fields' own `defaultValue`s and the untouched blank
          // `version` text field, exactly as an operator who only edited the
          // name would actually submit.
          biome_kind: "custom",
          workload_type: "lxc",
          version: "",
        },
      ),
    );
  });

  it("renders the SAME delete confirm copy as BiomesPage's own hand-written ConfirmDialog", async () => {
    const { biomesPage, manifestScreen } = renderBiomesBoth();
    await within(biomesPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-biome-open-4"));
    fireEvent.click(screen.getByTestId("gough-biome-delete"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-open-4"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-delete"));

    const expectedConfirm =
      'Deleting "web" removes the definition. Nodes already running it are not reverted.';
    const manifestConfirm =
      "Delete this biome? Nodes running it will need reassignment.";

    // BiomesPage's own copy interpolates the biome's real name inline (not
    // the manifest's `{name}` mechanism — that token is ActionSpec-only,
    // never DeleteSpec); the manifest's DeleteSpec.confirm is a fixed
    // string, matching neither the wording nor the interpolation style.
    // Both are asserted for what they actually render, not forced equal —
    // see this file's module doc for why a real divergence is reported,
    // not papered over.
    expect(screen.getByText(expectedConfirm)).toBeInTheDocument();
    expect(screen.getByText(manifestConfirm)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// agents
// ---------------------------------------------------------------------------

/** `ip_address: null` is the absent-value cell. Addressed by `agent_id`,
 * never the row `id` (`AgentsPage`'s own module doc). */
const RAW_AGENT = {
  id: 1,
  agent_id: "3f2b-aa",
  hostname: "agent-1",
  status: "active",
  ip_address: null,
  last_heartbeat: "2026-01-01T00:00:00Z",
};

/** `hostname: null` — the row `fallback_fields` is FOR. Both renderers must
 * show `agent_id` instead, reproducing `agentColumns.tsx`'s own
 * `String(value || row.agent_id || row.id)` chain. */
const RAW_AGENT_NO_HOSTNAME = {
  id: 2,
  agent_id: "9c11-bb",
  hostname: null,
  status: "pending",
  ip_address: "10.0.0.20",
  last_heartbeat: null,
};

/**
 * Transcribed from `_AGENTS_COLUMNS`/`_AGENTS` in `gough/manifest.py`,
 * including `item_path`, `actions`, and the `hostname` column's
 * `fallback_fields`.
 */
const GOUGH_AGENTS_RESOURCE: ResourceDescriptor = {
  kind: "agents",
  label: "Agent",
  plural_label: "Agents",
  id_field: "agent_id",
  name_field: "hostname",
  transport: "typed",
  columns: [
    {
      field: "hostname",
      label: "Hostname",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      fallback_fields: ["agent_id", "id"],
    },
    {
      field: "status",
      label: "Status",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "ip_address",
      label: "IP address",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "last_heartbeat",
      label: "Last heartbeat",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No agents enrolled yet.",
  error_state: "Unable to load agents.",
  list: {
    path_bytes: "/api/v1/agents/",
    envelope: { keys: ["agents"] },
    pagination: "none",
  },
  item_path: {
    prefix: "/api/v1/agents",
    sample_id: "11111111-1111-1111-1111-111111111111",
  },
  detail: { tabs: ["Overview"] },
  actions: [
    {
      verb: "suspend",
      label: "Suspend",
      variant: "danger",
      requires: "manage",
      confirm: "Suspend this agent?",
      starts_operations: false,
      form: null,
      enabled_when_field: null,
      enabled_when_in: [],
    },
    {
      verb: "resume",
      label: "Resume",
      variant: "primary",
      requires: "manage",
      confirm: null,
      starts_operations: false,
      form: null,
      enabled_when_field: null,
      enabled_when_in: [],
    },
  ],
  create: null,
  edit: null,
  delete: null,
  relationships: [],
};

const GOUGH_MANIFEST_AGENTS: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "agents", label: "Agents" }] },
  resources: [GOUGH_AGENTS_RESOURCE],
  operations: GOUGH_OPERATIONS_SPEC,
  metrics: null,
  extensions: [],
};

function renderAgentsBoth(rows: unknown[]) {
  goughApi.listAgents.mockResolvedValue(rows);
  mockProxyRequest.mockResolvedValue({ agents: rows });

  const agentsPage = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <AgentsPage />
    </QueryClientProvider>,
  );
  const manifestScreen = render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_AGENTS}
        resource={GOUGH_AGENTS_RESOURCE}
      />
    </QueryClientProvider>,
  );
  return { agentsPage, manifestScreen };
}

describe("ManifestResourceScreen vs AgentsPage — agents", () => {
  it("renders an IDENTICAL table to AgentsPage: same headers, same row, including the absent cell", async () => {
    const { agentsPage, manifestScreen } = renderAgentsBoth([RAW_AGENT]);

    const agentsRow = await within(agentsPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(agentsPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Hostname",
      "Status",
      "IP address",
      "Last heartbeat",
    ]);

    for (const shared of ["agent-1", "active", "2026-01-01T00:00:00Z"]) {
      expect(within(agentsRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `ip_address: null` -> a dash on both sides, not blank.
    expect(within(agentsRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("reproduces agentColumns.tsx's hostname fallback chain via ColumnSpec.fallback_fields: hostname null -> shows agent_id on BOTH sides", async () => {
    const { agentsPage, manifestScreen } = renderAgentsBoth([
      RAW_AGENT_NO_HOSTNAME,
    ]);

    const agentsRow = await within(agentsPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(within(agentsRow).getByText("9c11-bb")).toBeInTheDocument();
    expect(within(manifestRow).getByText("9c11-bb")).toBeInTheDocument();
  });

  it("renders the operations panel identically to AgentsPage's own hand-written OperationsPanel", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([RAW_OPERATION]);
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const { agentsPage, manifestScreen } = renderAgentsBoth([RAW_AGENT]);

    for (const container of [agentsPage.container, manifestScreen.container]) {
      expect(
        await within(container).findByText("Operations"),
      ).toBeInTheDocument();
      expect(within(container).getByText("deployment")).toBeInTheDocument();
    }
  });

  it("renders the SAME row actions (Suspend/Resume) with matching labels and danger/primary variants", async () => {
    const { agentsPage, manifestScreen } = renderAgentsBoth([RAW_AGENT]);
    await within(agentsPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-agent-open-3f2b-aa"));
    fireEvent.click(screen.getByTestId("gough-manifest-agents-open-3f2b-aa"));

    for (const label of ["Suspend", "Resume"]) {
      expect(
        within(agentsPage.container).getByText(label, { selector: "button" }),
      ).toBeInTheDocument();
      expect(
        within(manifestScreen.container).getByText(label, {
          selector: "button",
        }),
      ).toBeInTheDocument();
    }

    // Suspend (danger on both sides) raises the AlertTriangle warning icon
    // in the confirm dialog; Resume (primary on both sides) does not — an
    // actual behavioural signal for variant parity, not a CSS-class
    // inspection this file's own convention avoids.
    fireEvent.click(screen.getByTestId("gough-agent-suspend"));
    expect(
      screen.getByTestId("gough-agent-confirm").querySelector("svg"),
    ).not.toBeNull();
    fireEvent.click(screen.getByTestId("gough-agent-confirm-cancel"));

    fireEvent.click(screen.getByTestId("gough-agent-resume"));
    expect(
      screen.getByTestId("gough-agent-confirm").querySelector("svg"),
    ).toBeNull();
    fireEvent.click(screen.getByTestId("gough-agent-confirm-cancel"));

    fireEvent.click(screen.getByTestId("gough-manifest-agents-action-suspend"));
    expect(
      screen
        .getByTestId("gough-manifest-agents-action-confirm")
        .querySelector("svg"),
    ).not.toBeNull();
    fireEvent.click(
      screen.getByTestId("gough-manifest-agents-action-confirm-cancel"),
    );

    fireEvent.click(screen.getByTestId("gough-manifest-agents-action-resume"));
    expect(
      screen
        .getByTestId("gough-manifest-agents-action-confirm")
        .querySelector("svg"),
    ).toBeNull();
  });

  it("FINDING (not fixed here): the manifest's action confirm COPY does not match AgentsPage's hand-written text — reported, not papered over", async () => {
    const { agentsPage, manifestScreen } = renderAgentsBoth([RAW_AGENT]);
    await within(agentsPage.container).findByTestId("datatable-row");
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-agent-open-3f2b-aa"));
    fireEvent.click(screen.getByTestId("gough-agent-suspend"));
    const handWrittenSuspendConfirm =
      "Suspending stops this agent from acting until it is resumed.";
    expect(
      within(screen.getByTestId("gough-agent-confirm")).getByText(
        handWrittenSuspendConfirm,
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("gough-manifest-agents-open-3f2b-aa"));
    fireEvent.click(screen.getByTestId("gough-manifest-agents-action-suspend"));
    // The manifest's OWN declared copy — genuinely different wording, per
    // `_AGENTS`'s `suspend` ActionSpec in `gough/manifest.py`. Scoped to its
    // own dialog testid, not a document-wide absence check — AgentsPage's
    // own dialog (opened above) is still mounted alongside it, and its text
    // legitimately remains in the document; the two dialogs' MESSAGES not
    // matching is the finding, not one supplanting the other.
    const manifestDialog = screen.getByTestId(
      "gough-manifest-agents-action-confirm",
    );
    expect(
      within(manifestDialog).getByText("Suspend this agent?"),
    ).toBeInTheDocument();
    expect(
      within(manifestDialog).queryByText(handWrittenSuspendConfirm),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// SUPPORTED_CAPABILITIES is now load-bearing for a REAL Gough resource
// ---------------------------------------------------------------------------

describe("ProductResourceRoute vs a REAL Gough resource — the widened gate actually routes", () => {
  it("nodes (operations + actions, both now SUPPORTED_CAPABILITIES) routes through ManifestResourceScreen, never the hand-written NodesPage fallback", async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes("/console/manifests")) {
        return Promise.resolve({
          data: {
            manifests: [
              {
                product_id: 7,
                product_type: "gough",
                manifest: GOUGH_MANIFEST_NODES,
              },
            ],
            count: 1,
          },
        });
      }
      if (url.includes("/operations")) {
        return Promise.resolve({ data: { operations: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    goughApi.listNodes.mockResolvedValue([RAW_NODE]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [RAW_NODE] },
    });

    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ProductResourceRoute
          productType="gough"
          kind="nodes"
          fallback={NodesPage}
        />
      </QueryClientProvider>,
    );

    // Manifest-routed: `ManifestResourceDetail`'s OWN testid prefix, only
    // reachable if `ManifestResourceScreen` rendered — never present if
    // `ProductResourceRoute` fell back to the hand-written `NodesPage`,
    // whose own row-open testid prefix (`gough-node-open`) is checked absent
    // below for the same reason.
    expect(
      await screen.findByTestId("gough-manifest-nodes-open-12"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("gough-node-open-12")).not.toBeInTheDocument();
  });
});

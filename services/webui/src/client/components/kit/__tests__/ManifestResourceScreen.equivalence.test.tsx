/**
 * The equivalence proof, now golden: does `ManifestResourceScreen`, fed
 * Gough's committed `ResourceDescriptor`s, render EXACTLY the output the
 * hand-written `NodesPage`/`BiomesPage`/`AgentsPage` used to produce?
 *
 * Phase 8 Step 3 left this FALSIFIED on purpose: the committed manifest's
 * `nodes` columns (id, name, state, posture, ipv4, created_at) were not the
 * set `nodeColumns.tsx` actually rendered (name, state, posture, ipv4,
 * hardware_tags) — a content gap in the Step 3 Python authoring, not a
 * renderer defect. Step 8 closed that gap in `gough/manifest.py`, and this
 * file was rewritten from asserting the gap to asserting it was gone —
 * headers AND a sample row's cells, including an absent-value cell,
 * identical between the manifest-driven render and the hand-written one.
 *
 * Phase 8 Step 5 frontend widened this file's scope past the table, side by
 * side against the hand-written pages:
 * - the operations panel (list/poll spec/cancel/logs) on all three screens;
 * - row actions, `{name}` confirm interpolation, and danger-variant styling
 *   on nodes AND agents;
 * - the biomes create AND edit forms, including their "New biome"/"Edit
 *   biome" modal titles;
 * - the agents `hostname` column's `fallback_fields` chain.
 *
 * Phase 8 Step 7 closed the two remaining exactness gaps (agents' suspend/
 * resume confirm copy in `gough/manifest.py`, and lowercase create/edit
 * modal titles), then DELETED `NodesPage.tsx`/`BiomesPage.tsx`/
 * `AgentsPage.tsx` — `declarative_console` is default-on, and every value
 * this file's own side-by-side comparisons asserted equal is preserved
 * below as a hardcoded expectation instead. This file no longer imports or
 * renders the hand-written pages (they no longer exist); every string it
 * asserts against `ManifestResourceScreen`'s own output is the exact value
 * the deleted hand-written screen used to produce, captured at the moment
 * both sides were last proven identical — a regression in either the
 * manifest data (`gough/manifest.py`) or the renderer changes these
 * fixtures/expectations, not silently drifts past them.
 *
 * The `*_RESOURCE` fixtures are still hand-transcriptions of
 * `services/portal-api/app/adapters/gough/manifest.py` (this worktree
 * cannot import Python — see `manifestTypes.contract.test.ts`'s module doc
 * for why cross-language checks in this repo read source as text instead).
 * Kept deliberately literal, field for field.
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

// The manifest-driven renderer reads through the generic byte proxy for
// LIST data...
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

// ...and through the generic typed portal routes (operations/actions/
// create/edit/delete) for everything mutating — `ManifestResourceDetail.tsx`
// /`ManifestCreateForm.tsx`/`useManifestOperations.ts` all call `lib/api`
// directly, never a product-specific API module.
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

/** Every `<th role="columnheader">` label, in DOM order. */
function headerLabels(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("columnheader")
    .map((th) => th.textContent?.trim() ?? "");
}

/** One operation, shaped exactly as the typed operations contract returns
 * it (`OperationLike` / Gough's own `GoughOperation`). */
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
  // Safe default: no test relies on operations rendering unless it sets
  // this explicitly, and the panel renders NOTHING for an empty array
  // (`OperationsPanel.tsx`'s own "hidden entirely" contract) — never a
  // false "operations: []" for a test that never asked about operations.
  mockApiGet.mockResolvedValue({ data: { operations: [] } });
});

// ---------------------------------------------------------------------------
// nodes
// ---------------------------------------------------------------------------

/** One node, shaped exactly as Gough's own raw JSON. `posture: null` is the
 * absent-value cell. */
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
 * including `item_path` and `actions`.
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

function renderNodes() {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_NODES}
        resource={GOUGH_NODES_RESOURCE}
      />
    </QueryClientProvider>,
  );
}

describe("ManifestResourceScreen — nodes (golden: matches the deleted NodesPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [RAW_NODE] },
    });
  });

  it("proxies the manifest's own committed list path", async () => {
    renderNodes();
    await waitFor(() => expect(mockProxyRequest).toHaveBeenCalled());
    expect(mockProxyRequest).toHaveBeenCalledWith(7, "GET", "api/v1/nodes/");
  });

  it("renders the same table the deleted NodesPage produced: same headers, same row, including the absent cell", async () => {
    const manifestScreen = renderNodes();
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "State",
      "Posture",
      "IPv4",
      "Tags",
    ]);

    for (const shared of ["rack-a-01", "ready", "10.0.0.12", "gpu"]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // The absent cell (`posture: null`) renders as a dash, not a blank, not
    // "Unknown" — matching NodesPage's own absent-value convention.
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("honours the manifest's own empty_state copy, not the generic fallback", async () => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [] },
    });

    const manifestScreen = renderNodes();

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

  it("renders the operations panel matching NodesPage's own hand-written OperationsPanel: same title, same operation kind/status, cancel control and logs disclosure both present", async () => {
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const manifestScreen = renderNodes();
    const container = manifestScreen.container;

    const panel = await within(container).findByText("Operations");
    expect(panel).toBeInTheDocument();
    expect(within(container).getByText("deployment")).toBeInTheDocument();
    // Non-terminal + cancelAllowed=true -> a Cancel control.
    expect(
      within(container).getByText("Cancel", { selector: "button" }),
    ).toBeInTheDocument();
    // showLogs=true -> the "Show logs" disclosure toggle.
    expect(within(container).getByText("Show logs")).toBeInTheDocument();
  });

  it("cancelling a live operation calls the SAME portal cancel route NodesPage's own mutation used", async () => {
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );
    mockApiPost.mockResolvedValue({ data: {} });

    const manifestScreen = renderNodes();

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

  it("renders the same row actions (Deploy/Evacuate/Reject) NodesPage did, and Deploy's confirm interpolates {name} to the byte-identical string NodesPage's own hand-written template produced", async () => {
    const manifestScreen = renderNodes();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

    for (const label of ["Deploy", "Evacuate", "Reject"]) {
      expect(
        within(manifestScreen.container).getByText(label, {
          selector: "button",
        }),
      ).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-deploy"));

    const expectedConfirm =
      'Deploying commissions this hardware and begins provisioning it. This affects node "rack-a-01".';
    expect(
      within(
        screen.getByTestId("gough-manifest-nodes-action-confirm"),
      ).getByText(expectedConfirm),
    ).toBeInTheDocument();
  });

  it("confirming Deploy dispatches through the SAME typed action route both the manifest renderer and the deleted NodesPage ultimately called", async () => {
    mockApiPost.mockResolvedValue({ data: { accepted: true } });

    const manifestScreen = renderNodes();
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
 * `_BIOME_FORM_FIELDS` in `gough/manifest.py`, which was itself the SAME
 * array the deleted `BiomesPage.tsx` passed to `FormModalBuilder`
 * (`biomeFields`) for both "New biome" and "Edit biome". */
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
    confirm:
      'Deleting "{name}" removes the definition. Nodes already running it are not reverted.',
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

function renderBiomes() {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_BIOMES}
        resource={GOUGH_BIOMES_RESOURCE}
      />
    </QueryClientProvider>,
  );
}

describe("ManifestResourceScreen — biomes (golden: matches the deleted BiomesPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { biomes: [RAW_BIOME] },
    });
  });

  it("renders the same table the deleted BiomesPage produced: same headers, same row, including the absent cell", async () => {
    const manifestScreen = renderBiomes();
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Active",
      "Kind",
      "Workload",
      "Version",
    ]);

    for (const shared of ["web", "active", "custom", "1.2.3"]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `workload_type: null` -> a dash, not blank.
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("renders the operations panel matching BiomesPage's own hand-written OperationsPanel", async () => {
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const manifestScreen = renderBiomes();

    expect(
      await within(manifestScreen.container).findByText("Operations"),
    ).toBeInTheDocument();
    expect(
      within(manifestScreen.container).getByText("deployment"),
    ).toBeInTheDocument();
  });

  it("renders a CREATE form matching BiomesPage's biomeFields exactly: same field labels, same select options, same submit label, lowercase 'New biome' title", async () => {
    const manifestScreen = renderBiomes();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-create"));

    expect(
      within(manifestScreen.container).getByRole("heading", {
        name: "New biome",
      }),
    ).toBeInTheDocument();
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
      within(manifestScreen.container).getByRole("button", {
        name: "Create",
      }),
    ).toBeInTheDocument();
  });

  it("renders an EDIT form matching BiomesPage exactly: same field set, submit label 'Save', lowercase 'Edit biome' title, and NEVER prefilled from the selected row", async () => {
    const manifestScreen = renderBiomes();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-open-4"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-edit"));

    expect(
      within(manifestScreen.container).getByRole("heading", {
        name: "Edit biome",
      }),
    ).toBeInTheDocument();
    const manifestNameInput = await within(
      manifestScreen.container,
    ).findByLabelText(/^Name\*$/);
    // Never prefilled from the row (real biome name is "web") — matching
    // BiomesPage's own behaviour exactly.
    expect(manifestNameInput).toHaveValue("");
    expect(
      within(manifestScreen.container).getByRole("button", { name: "Save" }),
    ).toBeInTheDocument();
  });

  it("submits the edit form's full field payload (react-libs' FormBuilder submits the whole form, not a diff) to the generic typed item route", async () => {
    mockApiPut.mockResolvedValue({ data: { id: "4" } });
    const manifestScreen = renderBiomes();
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

  it("renders the SAME delete confirm copy the deleted BiomesPage's own hand-written ConfirmDialog produced — {name} interpolated", async () => {
    const manifestScreen = renderBiomes();
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-biomes-open-4"));
    fireEvent.click(screen.getByTestId("gough-manifest-biomes-delete"));

    // Phase 8 Step 7: gough/manifest.py's biome DeleteSpec.confirm now
    // carries the same `{name}` token ActionSpec.confirm uses, and
    // ManifestResourceDetail.tsx's delete dialog interpolates it the same
    // way — byte-identical to what BiomesPage's own hand-written
    // `` `Deleting "${deleting.name}" removes the definition. Nodes already
    // running it are not reverted.` `` template produced.
    expect(
      within(manifestScreen.container).getByText(
        'Deleting "web" removes the definition. Nodes already running it are not reverted.',
      ),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// agents
// ---------------------------------------------------------------------------

/** `ip_address: null` is the absent-value cell. Addressed by `agent_id`,
 * never the row `id` (the deleted `AgentsPage`'s own module doc). */
const RAW_AGENT = {
  id: 1,
  agent_id: "3f2b-aa",
  hostname: "agent-1",
  status: "active",
  ip_address: null,
  last_heartbeat: "2026-01-01T00:00:00Z",
};

/** `hostname: null` — the row `fallback_fields` is FOR. Reproduces the
 * deleted `agentColumns.tsx`'s own `String(value || row.agent_id ||
 * row.id)` chain: must show `agent_id` instead. */
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
      confirm: "Suspending stops this agent from acting until it is resumed.",
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
      confirm: "Resuming returns this agent to service.",
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

function renderAgents(rows: unknown[]) {
  mockProxyRequest.mockResolvedValue({ agents: rows });

  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST_AGENTS}
        resource={GOUGH_AGENTS_RESOURCE}
      />
    </QueryClientProvider>,
  );
}

describe("ManifestResourceScreen — agents (golden: matches the deleted AgentsPage's own output)", () => {
  it("renders the same table the deleted AgentsPage produced: same headers, same row, including the absent cell", async () => {
    const manifestScreen = renderAgents([RAW_AGENT]);
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Hostname",
      "Status",
      "IP address",
      "Last heartbeat",
    ]);

    for (const shared of ["agent-1", "active", "2026-01-01T00:00:00Z"]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `ip_address: null` -> a dash, not blank.
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });

  it("reproduces the deleted agentColumns.tsx's hostname fallback chain via ColumnSpec.fallback_fields: hostname null -> shows agent_id", async () => {
    const manifestScreen = renderAgents([RAW_AGENT_NO_HOSTNAME]);
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(within(manifestRow).getByText("9c11-bb")).toBeInTheDocument();
  });

  it("renders the operations panel matching AgentsPage's own hand-written OperationsPanel", async () => {
    mockApiGet.mockImplementation((url: string) =>
      url.includes("/operations")
        ? Promise.resolve({ data: { operations: [RAW_OPERATION] } })
        : Promise.resolve({ data: {} }),
    );

    const manifestScreen = renderAgents([RAW_AGENT]);

    expect(
      await within(manifestScreen.container).findByText("Operations"),
    ).toBeInTheDocument();
    expect(
      within(manifestScreen.container).getByText("deployment"),
    ).toBeInTheDocument();
  });

  it("renders the same row actions (Suspend/Resume) AgentsPage did, with matching labels and danger/primary variants", async () => {
    const manifestScreen = renderAgents([RAW_AGENT]);
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-agents-open-3f2b-aa"));

    for (const label of ["Suspend", "Resume"]) {
      expect(
        within(manifestScreen.container).getByText(label, {
          selector: "button",
        }),
      ).toBeInTheDocument();
    }

    // Suspend (danger) raises the AlertTriangle warning icon in the confirm
    // dialog; Resume (primary) does not — an actual behavioural signal for
    // variant parity with AgentsPage's own danger/primary ConfirmDialog
    // usage, not a CSS-class inspection.
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

  it("renders the SAME action confirm COPY the deleted AgentsPage's hand-written text produced for BOTH suspend and resume — gough/manifest.py's own ActionSpec.confirm data (Phase 8 Step 7)", async () => {
    const manifestScreen = renderAgents([RAW_AGENT]);
    await within(manifestScreen.container).findByTestId("datatable-row");

    fireEvent.click(screen.getByTestId("gough-manifest-agents-open-3f2b-aa"));
    fireEvent.click(screen.getByTestId("gough-manifest-agents-action-suspend"));
    const manifestSuspendDialog = screen.getByTestId(
      "gough-manifest-agents-action-confirm",
    );
    expect(
      within(manifestSuspendDialog).getByText(
        "Suspending stops this agent from acting until it is resumed.",
      ),
    ).toBeInTheDocument();
    expect(
      within(manifestSuspendDialog).getByText("Suspend agent"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByTestId("gough-manifest-agents-action-confirm-cancel"),
    );

    fireEvent.click(screen.getByTestId("gough-manifest-agents-action-resume"));
    const manifestResumeDialog = screen.getByTestId(
      "gough-manifest-agents-action-confirm",
    );
    expect(
      within(manifestResumeDialog).getByText(
        "Resuming returns this agent to service.",
      ),
    ).toBeInTheDocument();
    expect(
      within(manifestResumeDialog).getByText("Resume agent"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// SUPPORTED_CAPABILITIES is load-bearing for REAL Gough resources, now the
// ONLY way these routes render at all (Phase 8 Step 7 deleted their
// hand-written fallbacks)
// ---------------------------------------------------------------------------

describe("ProductResourceRoute vs a REAL Gough resource — no fallback left, the manifest is the only path", () => {
  it("nodes (operations + actions, both within SUPPORTED_CAPABILITIES) routes through ManifestResourceScreen with no fallback prop given", async () => {
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
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [RAW_NODE] },
    });

    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ProductResourceRoute productType="gough" kind="nodes" />
      </QueryClientProvider>,
    );

    // Manifest-routed: `ManifestResourceDetail`'s own testid prefix, only
    // reachable if `ManifestResourceScreen` rendered — never present if
    // `ProductResourceRoute` fell through to `DefaultResourceFallback`'s
    // generic empty state, whose own testid is checked absent below.
    expect(
      await screen.findByTestId("gough-manifest-nodes-open-12"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("gough-nodes-unavailable"),
    ).not.toBeInTheDocument();
  });
});

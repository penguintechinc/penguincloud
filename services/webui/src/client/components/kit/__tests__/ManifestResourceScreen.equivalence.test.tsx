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
 * The `*_RESOURCE` fixtures below are hand-transcriptions of
 * `services/portal-api/app/adapters/gough/manifest.py` (this worktree
 * cannot import Python — see `manifestTypes.contract.test.ts`'s module doc
 * for why cross-language checks in this repo read source as text instead).
 * Kept deliberately literal, field for field, for the COLUMNS/list/id
 * fields the table-equivalence proof needs; `actions`/`create`/`item_path`
 * are simplified to the empty/null case here (as schema v1's fixture
 * already did for `actions`) — this file's scope is the rendered TABLE,
 * not the detail drawer or its actions, which are covered instead by
 * `ManifestResourceScreen.test.tsx` and `ManifestResourceDetail.test.tsx`.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ManifestResourceScreen } from "../ManifestResourceScreen";
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

const goughOperationsApi = {
  listOperations: jest.fn(),
  performAction: jest.fn(),
};
jest.mock("../../../api/resources/goughOperations", () => ({
  goughOperationsApi,
}));

// The manifest-driven renderer reads through the generic byte proxy.
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
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

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
  goughOperationsApi.listOperations.mockResolvedValue([]);
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

/** Transcribed from `_NODES_COLUMNS`/`_NODES` in `gough/manifest.py`. */
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
  item_path: null,
  detail: { tabs: ["Overview", "Tags", "Biomes"] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const GOUGH_MANIFEST_NODES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "nodes", label: "Nodes" }] },
  resources: [GOUGH_NODES_RESOURCE],
  operations: null,
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

/** Transcribed from `_BIOMES_COLUMNS`/`_BIOMES` in `gough/manifest.py`. */
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
  item_path: null,
  detail: { tabs: ["Overview", "Eligibility"] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const GOUGH_MANIFEST_BIOMES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "biomes", label: "Biomes" }] },
  resources: [GOUGH_BIOMES_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs BiomesPage — biomes", () => {
  beforeEach(() => {
    goughApi.listBiomes.mockResolvedValue([RAW_BIOME]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { biomes: [RAW_BIOME] },
    });
  });

  it("renders an IDENTICAL table to BiomesPage: same headers, same row, including the absent cell", async () => {
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

/** Transcribed from `_AGENTS_COLUMNS`/`_AGENTS` in `gough/manifest.py`. */
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
  item_path: null,
  detail: { tabs: ["Overview"] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const GOUGH_MANIFEST_AGENTS: ConsoleManifest = {
  manifest_version: 2,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "agents", label: "Agents" }] },
  resources: [GOUGH_AGENTS_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs AgentsPage — agents", () => {
  beforeEach(() => {
    goughApi.listAgents.mockResolvedValue([RAW_AGENT]);
    mockProxyRequest.mockResolvedValue({ agents: [RAW_AGENT] });
  });

  it("renders an IDENTICAL table to AgentsPage: same headers, same row, including the absent cell", async () => {
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
});

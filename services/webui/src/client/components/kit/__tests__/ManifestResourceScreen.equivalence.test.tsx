/**
 * The falsification test: does `ManifestResourceScreen`, fed Gough's
 * committed `nodes` `ResourceDescriptor`, reproduce hand-written
 * `NodesPage`'s rendered table?
 *
 * The `GOUGH_NODES_RESOURCE` fixture below is a hand-transcription of
 * `_NODES_COLUMNS`/`_NODES` in `services/portal-api/app/adapters/gough/
 * manifest.py` (this worktree cannot import Python — see
 * `manifestTypes.contract.test.ts`'s module doc for why cross-language
 * checks in this repo read source as text instead). Kept deliberately
 * literal, field for field, rather than "equivalent-looking", so a
 * discrepancy between this fixture and the real manifest is a transcription
 * bug to fix, not a design choice to defend.
 *
 * Result: NOT byte-equivalent, and that is the finding. The renderer
 * reproduces whatever the manifest declares, faithfully — proven below for
 * every column the two sets share. But the COMMITTED manifest's `nodes`
 * columns (id, name, state, posture, ipv4, created_at) are not the same set
 * `nodeColumns.tsx` renders (name, state, posture, ipv4, hardware_tags):
 * the manifest adds `id`/`created_at` and omits `hardware_tags`/tags
 * entirely. That is a content gap in the Step 3 Python authoring, not a
 * renderer defect — see the Step 3 report.
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

// The hand-written page reads through `goughApi`.
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
// file would require `NodesPage` (and its transitive `goughOperationsApi`
// mock factory) before the `const`s those factories close over are
// assigned, the same ordering `GoughScreens.test.tsx` already follows.
import NodesPage from "../../../pages/products/gough/NodesPage";

/** One node, shaped exactly as Gough's own raw JSON — both renderers see
 * the identical row for the columns they share. */
const RAW_NODE = {
  id: 12,
  name: "rack-a-01",
  state: "ready",
  posture: "compliant",
  ipv4: "10.0.0.12",
  hardware_tags: ["gpu"],
  created_at: "2026-01-01T00:00:00Z",
};

/**
 * Transcribed from `_NODES_COLUMNS`/`_NODES` in
 * `services/portal-api/app/adapters/gough/manifest.py` — see this file's
 * module doc.
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
      field: "id",
      label: "ID",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
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
      field: "created_at",
      label: "Enrolled",
      sortable: false,
      cell: { kind: "timestamp", styles: [], relative: true },
      absent_as: "dash",
    },
  ],
  empty_state: "No nodes enrolled yet.",
  error_state: "Unable to load nodes.",
  list: {
    path_bytes: "/api/v1/nodes/",
    envelope_key: "nodes",
    pagination: "cursor",
  },
  detail: { tabs: ["Overview", "Tags", "Biomes"] },
  actions: [],
  create: null,
  delete: {
    confirm: "Decommission this node? This cannot be undone.",
    requires: "manage",
  },
  relationships: [],
};

const GOUGH_MANIFEST: ConsoleManifest = {
  manifest_version: 1,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [{ kind: "nodes", label: "Nodes" }] },
  resources: [GOUGH_NODES_RESOURCE],
  // Kept null deliberately: the operations panel is exercised on its own
  // terms in `useManifestOperations.test.tsx`. Leaving it in would require
  // mocking a second (typed-route) data source this test does not need to
  // prove table equivalence.
  operations: null,
  metrics: null,
  extensions: [],
};

function renderBoth() {
  const nodesPageClient = createAppQueryClient();
  const manifestClient = createAppQueryClient();

  const nodesPage = render(
    <QueryClientProvider client={nodesPageClient}>
      <NodesPage />
    </QueryClientProvider>,
  );
  const manifestScreen = render(
    <QueryClientProvider client={manifestClient}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={GOUGH_MANIFEST}
        resource={GOUGH_NODES_RESOURCE}
      />
    </QueryClientProvider>,
  );
  return { nodesPage, manifestScreen };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
  goughApi.listNodes.mockResolvedValue([RAW_NODE]);
  goughOperationsApi.listOperations.mockResolvedValue([]);
  mockProxyRequest.mockResolvedValue({
    status: "success",
    data: { nodes: [RAW_NODE] },
  });
});

describe("ManifestResourceScreen vs NodesPage — nodes", () => {
  it("proxies the exact path NodesPage's own goughPaths.ts pins", async () => {
    renderBoth();
    await waitFor(() => expect(mockProxyRequest).toHaveBeenCalled());
    expect(mockProxyRequest).toHaveBeenCalledWith(7, "GET", "api/v1/nodes/");
  });

  it("renders identical cell text for every column the two sets share", async () => {
    const { nodesPage, manifestScreen } = renderBoth();

    // Scoped to the table ROW, not the whole page: NodesPage also renders
    // the node's name a second time as its `RowOpenButtons` label, which
    // `findByText` would otherwise reject as an ambiguous match.
    const nodesRow = await within(nodesPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    for (const shared of ["rack-a-01", "ready", "compliant", "10.0.0.12"]) {
      expect(within(nodesRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }
  });

  it("FALSIFIED: the committed manifest's column set is not NodesPage's column set", async () => {
    const { nodesPage, manifestScreen } = renderBoth();
    await waitFor(() => expect(mockProxyRequest).toHaveBeenCalled());
    await screen.findAllByText("rack-a-01");

    // NodesPage shows the node's hardware tags; the manifest has no `tags`
    // column at all for `nodes` (see `_NODES_COLUMNS` in gough/manifest.py).
    expect(within(nodesPage.container).getByText("gpu")).toBeInTheDocument();
    expect(
      within(manifestScreen.container).queryByText("gpu"),
    ).not.toBeInTheDocument();

    // The manifest shows `id`/`created_at` ("ID"/"Enrolled" headers);
    // NodesPage's hand-written `nodeColumns.tsx` has neither.
    expect(
      within(manifestScreen.container).getByText("ID"),
    ).toBeInTheDocument();
    expect(
      within(manifestScreen.container).getByText("Enrolled"),
    ).toBeInTheDocument();
    expect(
      within(nodesPage.container).queryByText("ID"),
    ).not.toBeInTheDocument();
    expect(
      within(nodesPage.container).queryByText("Enrolled"),
    ).not.toBeInTheDocument();
  });

  it("honours the manifest's own empty_state copy, not the generic fallback", async () => {
    goughApi.listNodes.mockResolvedValue([]);
    mockProxyRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [] },
    });

    const { manifestScreen } = renderBoth();

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
          manifest={GOUGH_MANIFEST}
          resource={GOUGH_NODES_RESOURCE}
        />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("Unable to load nodes."),
    ).toBeInTheDocument();
  });
});

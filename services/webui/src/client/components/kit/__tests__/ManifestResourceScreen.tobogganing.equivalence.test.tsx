/**
 * The equivalence proof for Tobogganing: does `ManifestResourceScreen`, fed
 * the committed `tobogganing/manifest.py` descriptors, reproduce every
 * hand-written Tobogganing screen's rendered table exactly?
 *
 * Sibling to `ManifestResourceScreen.equivalence.test.tsx` (Gough) rather
 * than an extension of it — Jest gives each test file its own module
 * registry, so a second file is the cheapest way to mock a DIFFERENT api
 * module (`api/resources/tobogganing` vs `api/resources/gough`) without the
 * two mock factories colliding in one file. Assertion style is identical:
 * this proof compares rendered TEXT/values (header labels + cell text), not
 * DOM markup or CSS classes — see this module's per-resource comments for
 * why that specifically matters for `status`/`action` (colour-coded spans
 * on the hand-written side, plain text on the manifest side, matching
 * Gough's own `_NODES_COLUMNS` precedent of never fabricating a style map).
 *
 * All six Tobogganing resources are `transport: "proxy"`, `item_path: null`
 * (no detail view), `pagination: "none"`, with a BARE single-key envelope —
 * unlike Gough's mix of enveloped (`{data: {nodes: [...]}}`) and bare
 * (`{agents: [...]}`) shapes. Only 5 of the 6 kinds have a hand-written
 * screen to compare against; `blockpage_route` has none (see
 * `tobogganing/manifest.py`'s module docstring) and is out of scope here.
 *
 * The `*_RESOURCE` fixtures below are hand-transcriptions of
 * `services/portal-api/app/adapters/tobogganing/manifest.py` — this
 * worktree cannot import Python, so field/label/cell/absent_as/order are
 * copied by hand, the same technique the Gough file already documents.
 */
import { render, screen, within } from "@testing-library/react";
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

// The hand-written pages read through `tobogganingApi`.
const tobogganingApi = {
  listClients: jest.fn(),
  listClusters: jest.fn(),
  listPeers: jest.fn(),
  listBlockPages: jest.fn(),
  listSwgPolicies: jest.fn(),
  createBlockPage: jest.fn(),
  updateBlockPage: jest.fn(),
  previewBlockPage: jest.fn(),
  publishBlockPage: jest.fn(),
  setSwgPolicy: jest.fn(),
};
jest.mock("../../../api/resources/tobogganing", () => ({ tobogganingApi }));

// The manifest-driven renderer reads through the generic byte proxy.
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

// Imported after the mocks above are set up — an `import` at the top of the
// file would require the pages (and their transitive `tobogganingApi`
// mock factory) before the `const`s those factories close over are
// assigned, the same ordering the Gough equivalence file already follows.
import ClientsPage from "../../../pages/products/tobogganing/ClientsPage";
import ClustersPage from "../../../pages/products/tobogganing/ClustersPage";
import PeersPage from "../../../pages/products/tobogganing/PeersPage";
import BlockPagesPage from "../../../pages/products/tobogganing/BlockPagesPage";
import SwgPolicyPage from "../../../pages/products/tobogganing/SwgPolicyPage";

/** Every `<th role="columnheader">` label, in DOM order. */
function headerLabels(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("columnheader")
    .map((th) => th.textContent?.trim() ?? "");
}

const CONNECTED = {
  data: [{ id: 7, product_type: "tobogganing" }],
  isLoading: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue(CONNECTED);
});

// ---------------------------------------------------------------------------
// sdwan_client
// ---------------------------------------------------------------------------

/** One client, shaped exactly as Tobogganing's own raw JSON. `cluster_id:
 * null` is the absent-value cell — an enrolled-but-unassigned client, a real
 * state `clientColumns.tsx`'s own comment calls out. */
const RAW_CLIENT = {
  id: "client-1",
  name: "branch-nyc",
  status: "active",
  type: "docker",
  cluster_id: null,
  last_seen: "2026-08-09T01:00:00Z",
};

/** Transcribed from `_SDWAN_CLIENT_COLUMNS`/`_SDWAN_CLIENT` in
 * `tobogganing/manifest.py`. */
const TOBOGGANING_CLIENT_RESOURCE: ResourceDescriptor = {
  kind: "sdwan_client",
  label: "Client",
  plural_label: "Clients",
  id_field: "id",
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
      field: "status",
      label: "Status",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "type",
      label: "Type",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "cluster_id",
      label: "Cluster",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "last_seen",
      label: "Last seen",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No SD-WAN clients enrolled yet.",
  error_state: "Unable to load SD-WAN clients.",
  list: {
    path_bytes: "/api/v1/sdwan/clients",
    envelope: { keys: ["clients"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const TOBOGGANING_MANIFEST_CLIENTS: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "sdwan_client", label: "Clients" }] },
  resources: [TOBOGGANING_CLIENT_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs ClientsPage — sdwan_client", () => {
  beforeEach(() => {
    tobogganingApi.listClients.mockResolvedValue([RAW_CLIENT]);
    mockProxyRequest.mockResolvedValue({ clients: [RAW_CLIENT] });
  });

  it("proxies the exact path ClientsPage's own tobogganingPaths.ts pins", async () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_CLIENTS}
          resource={TOBOGGANING_CLIENT_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await screen.findByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sdwan/clients",
    );
  });

  it("renders an IDENTICAL table to ClientsPage: same headers, same row, including the absent cell", async () => {
    const clientsPage = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ClientsPage />
      </QueryClientProvider>,
    );
    const manifestScreen = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_CLIENTS}
          resource={TOBOGGANING_CLIENT_RESOURCE}
        />
      </QueryClientProvider>,
    );

    const clientsRow = await within(clientsPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(clientsPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Type",
      "Cluster",
      "Last seen",
    ]);

    // Every shared value, verbatim — including "active", which the
    // hand-written side colours via `statusCell` and the manifest side
    // renders as plain text; the TEXT is identical either way.
    for (const shared of ["branch-nyc", "active", "docker"]) {
      expect(within(clientsRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `cluster_id: null` -> a dash on both sides, not blank.
    expect(within(clientsRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// sdwan_cluster
// ---------------------------------------------------------------------------

/** `client_count: null` is the absent-value cell — the `number` cell kind's
 * absence path, distinct from Gough's `tags`/`count` kinds. */
const RAW_CLUSTER = {
  id: "cluster-1",
  name: "us-east-1",
  status: "healthy",
  region: "us-east",
  datacenter: "dc-3",
  client_count: null,
};

/** Transcribed from `_SDWAN_CLUSTER_COLUMNS`/`_SDWAN_CLUSTER` in
 * `tobogganing/manifest.py`. */
const TOBOGGANING_CLUSTER_RESOURCE: ResourceDescriptor = {
  kind: "sdwan_cluster",
  label: "Cluster",
  plural_label: "Clusters",
  id_field: "id",
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
      field: "status",
      label: "Status",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "region",
      label: "Region",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "datacenter",
      label: "Datacenter",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "client_count",
      label: "Clients",
      sortable: false,
      cell: { kind: "number", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No SD-WAN clusters defined yet.",
  error_state: "Unable to load SD-WAN clusters.",
  list: {
    path_bytes: "/api/v1/sdwan/clusters",
    envelope: { keys: ["clusters"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const TOBOGGANING_MANIFEST_CLUSTERS: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "sdwan_cluster", label: "Clusters" }] },
  resources: [TOBOGGANING_CLUSTER_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs ClustersPage — sdwan_cluster", () => {
  beforeEach(() => {
    tobogganingApi.listClusters.mockResolvedValue([RAW_CLUSTER]);
    mockProxyRequest.mockResolvedValue({ clusters: [RAW_CLUSTER] });
  });

  it("proxies the exact path ClustersPage's own tobogganingPaths.ts pins", async () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_CLUSTERS}
          resource={TOBOGGANING_CLUSTER_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await screen.findByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sdwan/clusters",
    );
  });

  it("renders an IDENTICAL table to ClustersPage: same headers, same row, including the absent cell", async () => {
    const clustersPage = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ClustersPage />
      </QueryClientProvider>,
    );
    const manifestScreen = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_CLUSTERS}
          resource={TOBOGGANING_CLUSTER_RESOURCE}
        />
      </QueryClientProvider>,
    );

    const clustersRow = await within(clustersPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(clustersPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Region",
      "Datacenter",
      "Clients",
    ]);

    for (const shared of ["us-east-1", "healthy", "us-east", "dc-3"]) {
      expect(within(clustersRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `client_count: null` -> a dash on both sides, never a false "0".
    expect(within(clustersRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// wireguard_peer
// ---------------------------------------------------------------------------

/** `ip_address: null` is the absent-value cell — a peer that has not yet
 * negotiated a tunnel address. Addressed by `node_id`; there is no `id`. */
const RAW_PEER = {
  node_id: "node-7",
  public_key: "AbCdEf0123456789==",
  ip_address: null,
};

/** Transcribed from `_WIREGUARD_PEER_COLUMNS`/`_WIREGUARD_PEER` in
 * `tobogganing/manifest.py`. */
const TOBOGGANING_PEER_RESOURCE: ResourceDescriptor = {
  kind: "wireguard_peer",
  label: "Peer",
  plural_label: "WireGuard Peers",
  id_field: "node_id",
  name_field: "node_id",
  transport: "proxy",
  columns: [
    {
      field: "node_id",
      label: "Node",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
    },
    {
      field: "public_key",
      label: "Public key",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "ip_address",
      label: "Tunnel IP",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No WireGuard peers enrolled yet.",
  error_state: "Unable to load WireGuard peers.",
  list: {
    path_bytes: "/api/v1/sdwan/wireguard/peers",
    envelope: { keys: ["peers"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const TOBOGGANING_MANIFEST_PEERS: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "wireguard_peer", label: "WireGuard Peers" }] },
  resources: [TOBOGGANING_PEER_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs PeersPage — wireguard_peer", () => {
  beforeEach(() => {
    tobogganingApi.listPeers.mockResolvedValue([RAW_PEER]);
    mockProxyRequest.mockResolvedValue({ peers: [RAW_PEER] });
  });

  it("proxies the exact path PeersPage's own tobogganingPaths.ts pins", async () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_PEERS}
          resource={TOBOGGANING_PEER_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await screen.findByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sdwan/wireguard/peers",
    );
  });

  it("renders an IDENTICAL table to PeersPage: same headers, same row, including the absent cell", async () => {
    const peersPage = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <PeersPage />
      </QueryClientProvider>,
    );
    const manifestScreen = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_PEERS}
          resource={TOBOGGANING_PEER_RESOURCE}
        />
      </QueryClientProvider>,
    );

    const peersRow = await within(peersPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(peersPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Node",
      "Public key",
      "Tunnel IP",
    ]);

    // Shared values, verbatim — including the public key, which the
    // hand-written side wraps in a monospace span; the manifest side does
    // not, but the rendered TEXT is identical.
    for (const shared of ["node-7", "AbCdEf0123456789=="]) {
      expect(within(peersRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `ip_address: null` -> a dash on both sides, not blank.
    expect(within(peersRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// block_page
// ---------------------------------------------------------------------------

/** `updated_by: null` is the absent-value cell — a freshly created page no
 * one has edited yet. */
const RAW_BLOCK_PAGE = {
  id: "bp-1",
  name: "generic-block",
  status: "published",
  version: 3,
  updated_by: null,
  updated_at: "2026-02-01T00:00:00Z",
};

/** Transcribed from `_BLOCK_PAGE_COLUMNS`/`_BLOCK_PAGE` in
 * `tobogganing/manifest.py`. */
const TOBOGGANING_BLOCK_PAGE_RESOURCE: ResourceDescriptor = {
  kind: "block_page",
  label: "Block Page",
  plural_label: "Block Pages",
  id_field: "id",
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
      field: "status",
      label: "Status",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "version",
      label: "Version",
      sortable: false,
      cell: { kind: "number", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "updated_by",
      label: "Updated by",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "updated_at",
      label: "Updated",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No block pages defined yet.",
  error_state: "Unable to load block pages.",
  list: {
    path_bytes: "/api/v1/sase/blockpages/pages",
    envelope: { keys: ["pages"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const TOBOGGANING_MANIFEST_BLOCK_PAGES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "block_page", label: "Block Pages" }] },
  resources: [TOBOGGANING_BLOCK_PAGE_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs BlockPagesPage — block_page", () => {
  beforeEach(() => {
    tobogganingApi.listBlockPages.mockResolvedValue([RAW_BLOCK_PAGE]);
    mockProxyRequest.mockResolvedValue({ pages: [RAW_BLOCK_PAGE] });
  });

  it("proxies the exact path BlockPagesPage's own tobogganingPaths.ts pins", async () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_BLOCK_PAGES}
          resource={TOBOGGANING_BLOCK_PAGE_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await screen.findByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sase/blockpages/pages",
    );
  });

  it("renders an IDENTICAL table to BlockPagesPage: same headers, same row, including the absent cell", async () => {
    const blockPagesPage = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <BlockPagesPage />
      </QueryClientProvider>,
    );
    const manifestScreen = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_BLOCK_PAGES}
          resource={TOBOGGANING_BLOCK_PAGE_RESOURCE}
        />
      </QueryClientProvider>,
    );

    const blockPagesRow = await within(blockPagesPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(blockPagesPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Version",
      "Updated by",
      "Updated",
    ]);

    // Every shared value, verbatim — including "published", which the
    // hand-written side colours via its own `STATUS_STYLES` map and the
    // manifest side renders as plain text; the TEXT is identical.
    for (const shared of [
      "generic-block",
      "published",
      "3",
      "2026-02-01T00:00:00Z",
    ]) {
      expect(within(blockPagesRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `updated_by: null` -> a dash on both sides, not blank.
    expect(within(blockPagesRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// swg_policy
// ---------------------------------------------------------------------------

/**
 * `scope_id: null` is the absent-value cell — deliberately paired with
 * `scope: "group"`, NOT `"tenant"`. `swgPolicyColumns.tsx`'s `scope_id`
 * column renders "Everyone" (not a dash) when `scope_id` is absent AND
 * `row.scope === "tenant"` — a value computed from a second field on the
 * same row, which this schema's plain field-to-cell binding cannot express
 * (see `tobogganing/manifest.py`'s own comment on `_SWG_POLICY_COLUMNS`,
 * naming this exact gap). A `scope: "group"` row sidesteps that documented,
 * open gap rather than masking it: both sides render a dash for it, so this
 * fixture proves real parity on the case this schema version DOES cover,
 * without asserting past the one it does not.
 */
const RAW_SWG_POLICY = {
  id: "pol-1",
  category: "malware",
  action: "block",
  scope: "group",
  scope_id: null,
};

/** Transcribed from `_SWG_POLICY_COLUMNS`/`_SWG_POLICY` in
 * `tobogganing/manifest.py`. Unlike every other resource here, ALL FOUR
 * columns — including the name field, `category` — carry `absent_as:
 * "dash"` in the Python source; transcribed faithfully rather than
 * "corrected" to match the other resources' shape. */
const TOBOGGANING_SWG_POLICY_RESOURCE: ResourceDescriptor = {
  kind: "swg_policy",
  label: "SWG Policy",
  plural_label: "SWG Policies",
  id_field: "id",
  name_field: "category",
  transport: "proxy",
  columns: [
    {
      field: "category",
      label: "Category",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "action",
      label: "Action",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "scope",
      label: "Scope",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
    {
      field: "scope_id",
      label: "Applies to",
      sortable: false,
      cell: { kind: "text", styles: [], relative: false },
      absent_as: "dash",
    },
  ],
  empty_state: "No SWG policies defined yet.",
  error_state: "Unable to load SWG policies.",
  list: {
    path_bytes: "/api/v1/sase/swg/policy",
    envelope: { keys: ["policies"] },
    pagination: "none",
  },
  item_path: null,
  detail: { tabs: [] },
  actions: [],
  create: null,
  delete: null,
  relationships: [],
};

const TOBOGGANING_MANIFEST_SWG_POLICIES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "swg_policy", label: "SWG Policy" }] },
  resources: [TOBOGGANING_SWG_POLICY_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [],
};

describe("ManifestResourceScreen vs SwgPolicyPage — swg_policy", () => {
  beforeEach(() => {
    tobogganingApi.listSwgPolicies.mockResolvedValue([RAW_SWG_POLICY]);
    mockProxyRequest.mockResolvedValue({ policies: [RAW_SWG_POLICY] });
  });

  it("proxies the exact path SwgPolicyPage's own tobogganingPaths.ts pins", async () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_SWG_POLICIES}
          resource={TOBOGGANING_SWG_POLICY_RESOURCE}
        />
      </QueryClientProvider>,
    );
    await screen.findByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sase/swg/policy",
    );
  });

  it("renders an IDENTICAL table to SwgPolicyPage: same headers, same row, including the absent cell", async () => {
    const swgPolicyPage = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <SwgPolicyPage />
      </QueryClientProvider>,
    );
    const manifestScreen = render(
      <QueryClientProvider client={createAppQueryClient()}>
        <ManifestResourceScreen
          productType="tobogganing"
          productLabel="Tobogganing"
          manifest={TOBOGGANING_MANIFEST_SWG_POLICIES}
          resource={TOBOGGANING_SWG_POLICY_RESOURCE}
        />
      </QueryClientProvider>,
    );

    const swgPolicyRow = await within(swgPolicyPage.container).findByTestId(
      "datatable-row",
    );
    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual(
      headerLabels(swgPolicyPage.container),
    );
    expect(headerLabels(manifestScreen.container)).toEqual([
      "Category",
      "Action",
      "Scope",
      "Applies to",
    ]);

    // Every shared value, verbatim — including "block", which the
    // hand-written side colours via its own `ACTION_STYLES` map and the
    // manifest side renders as plain text; the TEXT is identical.
    for (const shared of ["malware", "block", "group"]) {
      expect(within(swgPolicyRow).getByText(shared)).toBeInTheDocument();
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `scope_id: null` with `scope: "group"` -> a dash on both sides. (A
    // `scope: "tenant"` row would diverge — see the fixture's own comment.)
    expect(within(swgPolicyRow).getByText("—")).toBeInTheDocument();
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

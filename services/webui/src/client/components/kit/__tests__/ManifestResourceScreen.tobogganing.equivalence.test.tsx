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
 * (`{agents: [...]}`) shapes.
 *
 * Phase 8 Step 7 deleted the hand-written `ClientsPage`/`ClustersPage`/
 * `PeersPage`/`BlockPagesPage` — `declarative_console` is default-on, and
 * their read-only resources were already proven equivalence-exact below.
 * Those four sections are GOLDEN: each renders only `ManifestResourceScreen`
 * and asserts the exact header/cell/absent-value text the deleted
 * hand-written screen used to produce, captured at the moment both sides
 * were last proven identical. `swg_policy` was the one holdout — its
 * `SwgPolicyPage.tsx` stayed live because one column, `scope_id`, needed a
 * value computed from a SIBLING field (`row.scope`) a plain `ColumnSpec`
 * cannot express. That gap is now closed by a `cell` `ExtensionSlot`
 * (`tobogganing/manifest.py`'s `extensions` tuple, resolved by
 * `components/extensions/tobogganing/SwgPolicyScopeCell.tsx`), proven
 * byte-identical against the still-live `SwgPolicyPage` before it was
 * deleted in the same change that added the slot — so `swg_policy` is now
 * GOLDEN too, the fifth and last section, matching the other four's shape.
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

// The manifest-driven renderer reads through the generic byte proxy — the
// only api-layer mock this file needs now that every section (including
// `swg_policy`, since `SwgPolicyPage.tsx` was deleted) renders exclusively
// through `ManifestResourceScreen`.
const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

// The REAL production registration side effect for the `swg_policy` cell
// slot — proves the actual wiring (`tobogganing/manifest.py`'s declared
// slot resolving against the actually-registered `SwgPolicyScopeCell`), not
// a synthetic stand-in.
import "../../extensions/tobogganing/register";

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
 * state the deleted `clientColumns.tsx`'s own comment called out. */
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

describe("ManifestResourceScreen — sdwan_client (golden: matches the deleted ClientsPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({ clients: [RAW_CLIENT] });
  });

  it("proxies the manifest's own committed list path", async () => {
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

  it("renders the same table the deleted ClientsPage produced: same headers, same row, including the absent cell", async () => {
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

    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Type",
      "Cluster",
      "Last seen",
    ]);

    // Every value, verbatim — including "active", which ClientsPage's own
    // `statusCell` used to colour and the manifest renders as plain text;
    // the TEXT was already identical either way.
    for (const shared of ["branch-nyc", "active", "docker"]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `cluster_id: null` -> a dash, not blank.
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

describe("ManifestResourceScreen — sdwan_cluster (golden: matches the deleted ClustersPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({ clusters: [RAW_CLUSTER] });
  });

  it("proxies the manifest's own committed list path", async () => {
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

  it("renders the same table the deleted ClustersPage produced: same headers, same row, including the absent cell", async () => {
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

    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Region",
      "Datacenter",
      "Clients",
    ]);

    for (const shared of ["us-east-1", "healthy", "us-east", "dc-3"]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `client_count: null` -> a dash, never a false "0".
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

describe("ManifestResourceScreen — wireguard_peer (golden: matches the deleted PeersPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({ peers: [RAW_PEER] });
  });

  it("proxies the manifest's own committed list path", async () => {
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

  it("renders the same table the deleted PeersPage produced: same headers, same row, including the absent cell", async () => {
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

    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Node",
      "Public key",
      "Tunnel IP",
    ]);

    // Shared values, verbatim — including the public key, which
    // PeersPage's own hand-written cell wrapped in a monospace span; the
    // rendered TEXT was already identical.
    for (const shared of ["node-7", "AbCdEf0123456789=="]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `ip_address: null` -> a dash, not blank.
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

describe("ManifestResourceScreen — block_page (golden: matches the deleted BlockPagesPage's own output)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({ pages: [RAW_BLOCK_PAGE] });
  });

  it("proxies the manifest's own committed list path", async () => {
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

  it("renders the same table the deleted BlockPagesPage produced: same headers, same row, including the absent cell", async () => {
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

    const manifestRow = await within(manifestScreen.container).findByTestId(
      "datatable-row",
    );

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Name",
      "Status",
      "Version",
      "Updated by",
      "Updated",
    ]);

    // Every value, verbatim — including "published", which
    // BlockPagesPage's own `STATUS_STYLES` map used to colour and the
    // manifest renders as plain text; the TEXT was already identical.
    for (const shared of [
      "generic-block",
      "published",
      "3",
      "2026-02-01T00:00:00Z",
    ]) {
      expect(within(manifestRow).getByText(shared)).toBeInTheDocument();
    }

    // `updated_by: null` -> a dash, not blank.
    expect(within(manifestRow).getByText("—")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// swg_policy — the fifth and last GOLDEN section: SwgPolicyPage.tsx is now
// deleted, its one equivalence gap closed by a `cell` ExtensionSlot.
// ---------------------------------------------------------------------------

/**
 * `scope_id: null` paired with `scope: "tenant"` — the tenant-wide case
 * the deleted `swgPolicyColumns.tsx`'s own `scope_id` column rendered as
 * "Everyone", not a dash, because a tenant-scoped policy has no subject BY
 * DEFINITION. This was the one documented equivalence gap a plain
 * `ColumnSpec` could not express (computed from a SECOND field,
 * `row.scope`, on the same row — see `tobogganing/manifest.py`'s own
 * comment on `_SWG_POLICY_COLUMNS`), closed by declaring a `cell`
 * `ExtensionSlot` for this (resource, field) pair and registering
 * `SwgPolicyScopeCell` under `"tobogganing.scope_id"`. Proven byte-identical
 * against the still-live `SwgPolicyPage` before it was deleted (see this
 * file's own git history for that intermediate proof); asserted here
 * directly, the same golden-fixture shape the other four sections use.
 */
const RAW_SWG_POLICY_TENANT = {
  id: "pol-1",
  category: "malware",
  action: "block",
  scope: "tenant",
  scope_id: null,
};

/** Group- and user-scoped policies — `scope_id` present on both, so the
 * cell slot's own `value ? String(value) : ...` branch never reaches the
 * "Everyone"/dash decision at all. Proves the slot does not clobber the
 * ordinary, unaffected case for either non-tenant scope. */
const RAW_SWG_POLICY_GROUP = {
  id: "pol-2",
  category: "phishing",
  action: "soft_block",
  scope: "group",
  scope_id: "grp-eng",
};

const RAW_SWG_POLICY_USER = {
  id: "pol-3",
  category: "malware",
  action: "allow",
  scope: "user",
  scope_id: "user-42",
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

/** Transcribed from `TOBOGGANING_MANIFEST`'s `extensions` tuple in
 * `tobogganing/manifest.py` — the `cell` slot that closes the "Everyone"
 * gap this section used to sidestep. */
const TOBOGGANING_MANIFEST_SWG_POLICIES: ConsoleManifest = {
  manifest_version: 2,
  product_type: "tobogganing",
  display_name: "Tobogganing",
  nav: { items: [{ kind: "swg_policy", label: "SWG Policy" }] },
  resources: [TOBOGGANING_SWG_POLICY_RESOURCE],
  operations: null,
  metrics: null,
  extensions: [
    {
      slot: "cell",
      id: "scope_id",
      label: "Applies to",
      resource: "swg_policy",
      position: 0,
    },
  ],
};

describe("ManifestResourceScreen — swg_policy (golden: matches the deleted SwgPolicyPage's own output, cell slot included)", () => {
  beforeEach(() => {
    mockProxyRequest.mockResolvedValue({
      policies: [
        RAW_SWG_POLICY_TENANT,
        RAW_SWG_POLICY_GROUP,
        RAW_SWG_POLICY_USER,
      ],
    });
  });

  it("proxies the manifest's own committed list path", async () => {
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
    await screen.findAllByTestId("datatable-row");
    expect(mockProxyRequest).toHaveBeenCalledWith(
      7,
      "GET",
      "api/v1/sase/swg/policy",
    );
  });

  it("renders the same table the deleted SwgPolicyPage produced: same headers, same rows, including the cell-slot value", async () => {
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

    const rows = await within(manifestScreen.container).findAllByTestId(
      "datatable-row",
    );
    expect(rows).toHaveLength(3);
    const [tenantRow, groupRow, userRow] = rows;

    expect(headerLabels(manifestScreen.container)).toEqual([
      "Category",
      "Action",
      "Scope",
      "Applies to",
    ]);

    // `scope_id: null` with `scope: "tenant"` -> "Everyone", not a dash —
    // the cell slot's whole reason to exist. Byte-matches the deleted
    // `swgPolicyColumns.tsx`'s own `scope_id` render.
    expect(within(tenantRow!).getByText("malware")).toBeInTheDocument();
    expect(within(tenantRow!).getByText("block")).toBeInTheDocument();
    expect(within(tenantRow!).getByText("tenant")).toBeInTheDocument();
    expect(within(tenantRow!).getByText("Everyone")).toBeInTheDocument();

    // group/user: `scope_id` present -> the cell slot renders the raw id
    // verbatim, same as the default `text` cell always did. Not clobbered
    // by the slot's tenant-only branch.
    expect(within(groupRow!).getByText("phishing")).toBeInTheDocument();
    expect(within(groupRow!).getByText("group")).toBeInTheDocument();
    expect(within(groupRow!).getByText("grp-eng")).toBeInTheDocument();

    expect(within(userRow!).getByText("allow")).toBeInTheDocument();
    expect(within(userRow!).getByText("user")).toBeInTheDocument();
    expect(within(userRow!).getByText("user-42")).toBeInTheDocument();
  });
});

/**
 * `ManifestResourceDetail` — the row-open button, detail drawer, and the
 * drawer's own delete/action buttons, all gated on `resource.item_path`.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ManifestResourceDetail } from "../ManifestResourceDetail";
import api from "../../../lib/api";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { post: jest.fn(), delete: jest.fn(), put: jest.fn() },
}));

// Only exercised by the relationship-tab tests below (`useProductResource`,
// via `RelationshipChildTab`) — every other test in this file declares no
// `relationships`, so these mocks' default return values are never reached.
const mockIsProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
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

const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

const mockedApi = api as unknown as {
  post: jest.Mock;
  delete: jest.Mock;
  put: jest.Mock;
};

function resource(
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
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
    ],
    empty_state: "empty",
    error_state: "error",
    list: null,
    item_path: { prefix: "/api/v1/nodes", sample_id: "1" },
    detail: { tabs: [] },
    actions: [],
    create: null,
    delete: null,
    relationships: [],
    ...overrides,
  };
}

const ROWS = [{ id: "12", name: "rack-a-01", state: "ready" }];

function manifestFixture(resources: ResourceDescriptor[]): ConsoleManifest {
  return {
    manifest_version: 2,
    product_type: "gough",
    display_name: "Gough",
    nav: { items: [] },
    resources,
    operations: null,
    metrics: null,
    extensions: [],
  };
}

function renderDetail(
  res: ResourceDescriptor,
  watch?: (ids: string[]) => void,
  manifest: ConsoleManifest = manifestFixture([res]),
) {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceDetail
        productType="gough"
        tenantId={42}
        productId={7}
        manifest={manifest}
        resource={res}
        rows={ROWS}
        watch={watch}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
});

it("renders nothing when the resource declares no item_path", () => {
  const { container } = renderDetail(resource({ item_path: null }));
  expect(container).toBeEmptyDOMElement();
});

it("opens the drawer from the row-open button and shows the row's own facts", () => {
  renderDetail(resource());

  expect(
    screen.getByTestId("gough-manifest-nodes-open-12"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

  expect(screen.getByTestId("gough-manifest-nodes-drawer")).toBeInTheDocument();
  const facts = screen.getByTestId("gough-manifest-nodes-facts");
  expect(facts).toHaveTextContent("Name");
  expect(facts).toHaveTextContent("rack-a-01");
  expect(facts).toHaveTextContent("State");
  expect(facts).toHaveTextContent("ready");
});

it("closes on the drawer's own close button", () => {
  renderDetail(resource());
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-drawer-close"));
  expect(
    screen.queryByTestId("gough-manifest-nodes-drawer"),
  ).not.toBeInTheDocument();
});

it("deletes only after confirmation, through the generic typed delete route", async () => {
  mockedApi.delete.mockResolvedValue({ data: { deleted: true } });
  renderDetail(
    resource({ delete: { confirm: "Delete this node?", requires: "manage" } }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-delete"));

  expect(mockedApi.delete).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-delete-confirm-confirm"),
  );

  await waitFor(() =>
    expect(mockedApi.delete).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12",
    ),
  );
  // A successful delete closes the drawer too.
  expect(
    screen.queryByTestId("gough-manifest-nodes-drawer"),
  ).not.toBeInTheDocument();
});

it("performs an action only after confirmation, through the generic typed action route", async () => {
  mockedApi.post.mockResolvedValue({ data: { accepted: true } });
  renderDetail(
    resource({
      actions: [
        {
          verb: "evacuate",
          label: "Evacuate",
          variant: "danger",
          requires: "manage",
          confirm: "Evacuate this node?",
          starts_operations: false,
          enabled_when_in: [],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-evacuate"));

  expect(mockedApi.post).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-action-confirm-confirm"),
  );

  await waitFor(() =>
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12/actions/evacuate",
      {},
    ),
  );
});

it('hands the action\'s started operation ids to watch() for a mode="watch" resource', async () => {
  mockedApi.post.mockResolvedValue({
    data: { operations: [{ id: "op-1" }, { id: "op-2" }] },
  });
  const watch = jest.fn();
  renderDetail(
    resource({
      actions: [
        {
          verb: "snapshot",
          label: "Snapshot",
          variant: "primary",
          requires: "manage",
          confirm: "Snapshot this node?",
          starts_operations: true,
          enabled_when_in: [],
        },
      ],
    }),
    watch,
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-snapshot"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-action-confirm-confirm"),
  );

  await waitFor(() => expect(watch).toHaveBeenCalledWith(["op-1", "op-2"]));
});

it("falls back to the row's own id for the open-button label and drawer title when name_field is falsy", () => {
  // `??` (nullish coalescing), not `||` — the row's name field is simply
  // absent (undefined), not an empty string, which `??` would NOT fall
  // back on.
  const rows = [{ id: "13", state: "ready" }];
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceDetail
        productType="gough"
        tenantId={42}
        productId={7}
        manifest={manifestFixture([resource()])}
        resource={resource()}
        rows={rows}
      />
    </QueryClientProvider>,
  );

  expect(screen.getByTestId("gough-manifest-nodes-open-13")).toHaveTextContent(
    "13",
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-13"));
  expect(screen.getByText("Node 13")).toBeInTheDocument();
});

it("renders an array-valued fact joined, and a null-valued fact as absent, without crashing", () => {
  const res = resource({
    columns: [
      {
        field: "hardware_tags",
        label: "Tags",
        sortable: false,
        cell: { kind: "tags", styles: [], relative: false },
        absent_as: "dash",
      },
      {
        field: "posture",
        label: "Posture",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
        absent_as: "dash",
      },
    ],
  });
  const rows = [
    {
      id: "12",
      name: "rack-a-01",
      hardware_tags: ["gpu", "edge"],
      posture: null,
    },
  ];

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceDetail
        productType="gough"
        tenantId={42}
        productId={7}
        manifest={manifestFixture([res])}
        resource={res}
        rows={rows}
      />
    </QueryClientProvider>,
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  const facts = screen.getByTestId("gough-manifest-nodes-facts");
  expect(facts).toHaveTextContent("gpu, edge");
  // FactList itself renders a dash for the empty-string fact the null
  // posture produces.
  expect(facts).toHaveTextContent("—");
});

it("disables an action whose enabled_when_field predicate the selected row fails", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "resume",
          label: "Resume",
          variant: "default",
          requires: "manage",
          confirm: null,
          starts_operations: false,
          enabled_when_field: "state",
          enabled_when_in: ["suspended"],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  // The row's own `state` is "ready", not "suspended" — the button is
  // present but disabled, never hidden (an operator should see why an
  // action is unavailable, not wonder where it went).
  expect(
    screen.getByTestId("gough-manifest-nodes-action-resume"),
  ).toBeDisabled();
});

it("does not delete when the delete confirmation is dismissed", () => {
  renderDetail(
    resource({ delete: { confirm: "Delete this node?", requires: "manage" } }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-delete"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-delete-confirm-cancel"),
  );

  expect(mockedApi.delete).not.toHaveBeenCalled();
  // Dismissing only closes the confirm dialog — the drawer itself stays open.
  expect(screen.getByTestId("gough-manifest-nodes-drawer")).toBeInTheDocument();
});

it("does not act when the action confirmation is dismissed", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "evacuate",
          label: "Evacuate",
          variant: "danger",
          requires: "manage",
          confirm: "Evacuate this node?",
          starts_operations: false,
          enabled_when_in: [],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-evacuate"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-action-confirm-cancel"),
  );

  expect(mockedApi.post).not.toHaveBeenCalled();
});

it("treats a missing enabled_when_field row value as empty, not a crash", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "resume",
          label: "Resume",
          variant: "default",
          requires: "manage",
          confirm: null,
          starts_operations: false,
          enabled_when_field: "not_on_row",
          enabled_when_in: ["suspended"],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  expect(
    screen.getByTestId("gough-manifest-nodes-action-resume"),
  ).toBeDisabled();
});

it("renders no Edit button when the resource declares no edit form", () => {
  renderDetail(resource({ edit: null }));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  expect(
    screen.queryByTestId("gough-manifest-nodes-edit"),
  ).not.toBeInTheDocument();
});

it("opens the edit modal, submits, and PUTs the aliased payload to the generic typed item route — never prefilled from the selected row", async () => {
  mockedApi.put.mockResolvedValue({ data: { id: "12" } });
  renderDetail(
    resource({
      edit: {
        fields: [
          {
            name: "name",
            label: "Name",
            field_type: "text",
            required: true,
            options: [],
          },
        ],
        submit_label: "Save",
        field_aliases: [{ portal_name: "name", product_name: "node_name" }],
      },
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-edit"));

  // Never prefilled — BiomesPage's own FormModalBuilder opens blank for
  // Edit too, switching only title/submit label, not the field values.
  const nameInput = await screen.findByLabelText(/^Name\*$/);
  expect(nameInput).toHaveValue("");

  fireEvent.change(nameInput, { target: { value: "rack-a-02" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(mockedApi.put).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12",
      { node_name: "rack-a-02" },
    ),
  );
  await waitFor(() =>
    expect(screen.queryByLabelText(/^Name\*$/)).not.toBeInTheDocument(),
  );
});

it("closes the edit modal without submitting when its own Cancel is clicked", async () => {
  renderDetail(
    resource({
      edit: {
        fields: [
          {
            name: "name",
            label: "Name",
            field_type: "text",
            required: true,
            options: [],
          },
        ],
        submit_label: "Save",
        field_aliases: [],
      },
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-edit"));
  await screen.findByLabelText(/^Name\*$/);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(screen.queryByLabelText(/^Name\*$/)).not.toBeInTheDocument();
  expect(mockedApi.put).not.toHaveBeenCalled();
});

it("substitutes {name} in an action's confirm copy with the selected row's own name_field value, byte-exact with NodesPage's hand-written interpolation", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "deploy",
          label: "Deploy",
          variant: "danger",
          requires: "manage",
          confirm:
            'Deploying commissions this hardware and begins provisioning it. This affects node "{name}".',
          starts_operations: true,
          enabled_when_in: [],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-deploy"));

  expect(
    screen.getByText(
      'Deploying commissions this hardware and begins provisioning it. This affects node "rack-a-01".',
    ),
  ).toBeInTheDocument();
});

it("leaves any OTHER braced token in a confirm string verbatim — only {name} is interpreted", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "evacuate",
          label: "Evacuate",
          variant: "danger",
          requires: "manage",
          confirm: 'Evacuate "{name}"? {unrelated_token} stays as-is.',
          starts_operations: false,
          enabled_when_in: [],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-action-evacuate"));

  expect(
    screen.getByText('Evacuate "rack-a-01"? {unrelated_token} stays as-is.'),
  ).toBeInTheDocument();
});

it("disables an action that declares a form — unsupported without an approximated payload", () => {
  renderDetail(
    resource({
      actions: [
        {
          verb: "deploy",
          label: "Deploy",
          variant: "primary",
          requires: "manage",
          confirm: "Deploy?",
          starts_operations: true,
          form: { fields: [], submit_label: "Deploy", field_aliases: [] },
          enabled_when_in: [],
        },
      ],
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  expect(
    screen.getByTestId("gough-manifest-nodes-action-deploy"),
  ).toBeDisabled();
});

// --- RelationshipSpec child-list tabs -------------------------------------

function partsResource(
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
    kind: "parts",
    label: "Part",
    plural_label: "Parts",
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
    ],
    empty_state: "No parts.",
    error_state: "Unable to load parts.",
    list: {
      path_bytes: "/api/v1/parts/",
      envelope: { keys: ["parts"] },
      pagination: "none",
    },
    item_path: null,
    detail: { tabs: [] },
    actions: [],
    create: null,
    delete: null,
    relationships: [],
    ...overrides,
  };
}

it("declares no extra tab and no tablist at all when the resource declares no relationships — byte-identical to before RelationshipSpec rendering existed", () => {
  renderDetail(resource());
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

  expect(screen.getByTestId("gough-manifest-nodes-facts")).toBeInTheDocument();
  // DetailDrawer only renders a tablist once tabs.length > 1 — one
  // undeclared relationship means exactly one tab, so no tab bar at all.
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

it("renders one additional tab per RelationshipSpec, labelled from the child kind's plural_label, alongside Overview", () => {
  const nodesWithRel = resource({
    relationships: [{ child_kind: "parts", parent_field: "node_id" }],
  });
  renderDetail(
    nodesWithRel,
    undefined,
    manifestFixture([nodesWithRel, partsResource()]),
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

  expect(
    screen.getByTestId("gough-manifest-nodes-drawer-tab-overview"),
  ).toHaveTextContent("Overview");
  expect(
    screen.getByTestId("gough-manifest-nodes-drawer-tab-rel-parts"),
  ).toHaveTextContent("Parts");
  // Overview stays the tab shown by default.
  expect(screen.getByTestId("gough-manifest-nodes-facts")).toBeInTheDocument();
});

it("lists only child rows whose parent_field matches the open row's own id — a non-matching row is excluded (falsifiability)", async () => {
  mockProxyRequest.mockResolvedValue({
    parts: [
      { id: "p1", name: "Fan", node_id: "12" },
      { id: "p2", name: "Other-node's PSU", node_id: "99" },
    ],
  });
  const nodesWithRel = resource({
    relationships: [{ child_kind: "parts", parent_field: "node_id" }],
  });
  renderDetail(
    nodesWithRel,
    undefined,
    manifestFixture([nodesWithRel, partsResource()]),
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-drawer-tab-rel-parts"),
  );

  expect(await screen.findByText("Fan")).toBeInTheDocument();
  expect(screen.queryByText("Other-node's PSU")).not.toBeInTheDocument();
});

it("resets the active tab back to Overview when a different row is opened, even after switching tabs", async () => {
  mockProxyRequest.mockResolvedValue({
    parts: [{ id: "p1", name: "Fan", node_id: "12" }],
  });
  const nodesWithRel = resource({
    relationships: [{ child_kind: "parts", parent_field: "node_id" }],
  });
  renderDetail(
    nodesWithRel,
    undefined,
    manifestFixture([nodesWithRel, partsResource()]),
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-drawer-tab-rel-parts"),
  );
  await screen.findByText("Fan");

  fireEvent.click(screen.getByTestId("gough-manifest-nodes-drawer-close"));
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

  expect(screen.getByTestId("gough-manifest-nodes-facts")).toBeInTheDocument();
});

it("shows the child's own no-list message inside its relationship tab, rather than crashing, when the child kind has no list endpoint", () => {
  const nodesWithRel = resource({
    relationships: [{ child_kind: "parts", parent_field: "node_id" }],
  });
  renderDetail(
    nodesWithRel,
    undefined,
    manifestFixture([nodesWithRel, partsResource({ list: null })]),
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));
  fireEvent.click(
    screen.getByTestId("gough-manifest-nodes-drawer-tab-rel-parts"),
  );

  expect(screen.getByTestId("gough-parts-no-list")).toBeInTheDocument();
  expect(mockProxyRequest).not.toHaveBeenCalled();
});

it("skips a relationship naming a child_kind this manifest does not declare, rather than crashing", () => {
  const nodesWithGhostRel = resource({
    relationships: [{ child_kind: "ghost_kind", parent_field: "node_id" }],
  });
  renderDetail(
    nodesWithGhostRel,
    undefined,
    manifestFixture([nodesWithGhostRel]),
  );
  fireEvent.click(screen.getByTestId("gough-manifest-nodes-open-12"));

  expect(screen.getByTestId("gough-manifest-nodes-facts")).toBeInTheDocument();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

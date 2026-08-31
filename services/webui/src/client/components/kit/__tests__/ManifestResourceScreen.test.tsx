/**
 * `ManifestResourceScreen` behaviour not covered by the equivalence suite:
 * the no-`list` branch, the operations panel wiring, and id normalisation
 * off a resource's OWN `id_field` (not hardcoded `"id"` — Gough addresses
 * agents by `agent_id`).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ManifestResourceScreen } from "../ManifestResourceScreen";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

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

const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
  },
}));

function baseResource(
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
    kind: "agents",
    label: "Agent",
    plural_label: "Agents",
    id_field: "agent_id",
    name_field: "hostname",
    transport: "typed",
    columns: [
      {
        field: "agent_id",
        label: "Agent ID",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
      },
      {
        field: "hostname",
        label: "Hostname",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
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
    detail: { tabs: [] },
    actions: [],
    relationships: [],
    ...overrides,
  };
}

function manifest(
  resource: ResourceDescriptor,
  operations: ConsoleManifest["operations"] = null,
): ConsoleManifest {
  return {
    manifest_version: 1,
    product_type: "gough",
    display_name: "Gough",
    nav: { items: [{ kind: resource.kind, label: resource.plural_label }] },
    resources: [resource],
    operations,
    metrics: null,
    extensions: [],
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
});

it("normalises row id off the resource's own id_field, not a hardcoded 'id'", async () => {
  mockProxyRequest.mockResolvedValue({
    agents: [{ agent_id: "3f2b-aa", hostname: "agent-1" }],
  });
  const resource = baseResource();

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText("agent-1")).toBeInTheDocument());
  expect(screen.getAllByTestId("datatable-row")).toHaveLength(1);
});

it("renders a no-list message rather than crashing when the resource has no collection endpoint", () => {
  const resource = baseResource({ list: null });

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  expect(screen.getByTestId("gough-agents-no-list")).toBeInTheDocument();
  expect(mockProxyRequest).not.toHaveBeenCalled();
});

it("renders the operations panel read-only when the manifest declares cancel_allowed=false", async () => {
  mockProxyRequest.mockResolvedValue({ agents: [] });
  mockApiGet.mockResolvedValue({
    data: {
      operations: [
        {
          id: "op-1",
          kind: "suspend",
          state: "running",
          status: "running",
          is_terminal: false,
        },
      ],
    },
  });
  const resource = baseResource();

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource, {
          label: "Operations",
          poll_interval_seconds: 5,
          cancel_allowed: false,
          show_logs: false,
        })}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  expect(
    await screen.findByTestId("gough-manifest-agents-operations"),
  ).toBeInTheDocument();
  expect(mockApiGet).toHaveBeenCalledWith("/products/7/operations");
  // Read-only: OperationsSpec.cancel_allowed is false.
  expect(
    screen.queryByTestId("gough-manifest-agents-operation-cancel-op-1"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId("gough-manifest-agents-operation-logs-toggle-op-1"),
  ).not.toBeInTheDocument();
});

it("wires a real cancel control when the manifest declares cancel_allowed=true", async () => {
  mockProxyRequest.mockResolvedValue({ agents: [] });
  mockApiGet.mockResolvedValue({
    data: {
      operations: [
        {
          id: "op-1",
          kind: "suspend",
          state: "running",
          status: "running",
          is_terminal: false,
        },
      ],
    },
  });
  const resource = baseResource();

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource, {
          label: "Operations",
          poll_interval_seconds: 5,
          cancel_allowed: true,
          show_logs: true,
        })}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  const cancelButton = await screen.findByTestId(
    "gough-manifest-agents-operation-cancel-op-1",
  );
  fireEvent.click(cancelButton);
  await waitFor(() =>
    expect(mockApiPost).toHaveBeenCalledWith(
      "/products/7/operations/suspend/op-1/cancel",
    ),
  );

  // Opening the log disclosure exercises the injected useOperationLogs hook.
  mockApiGet.mockResolvedValue({ data: { logs: [{ message: "queued" }] } });
  fireEvent.click(
    screen.getByTestId("gough-manifest-agents-operation-logs-toggle-op-1"),
  );
  expect(await screen.findByText("queued")).toBeInTheDocument();
});

it("stays hidden when the manifest declares no operations", async () => {
  mockProxyRequest.mockResolvedValue({ agents: [] });
  const resource = baseResource();

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(mockProxyRequest).toHaveBeenCalled());
  expect(mockApiGet).not.toHaveBeenCalled();
});

it("renders a row-open button and detail drawer when the resource declares item_path", async () => {
  mockProxyRequest.mockResolvedValue({
    agents: [{ agent_id: "3f2b-aa", hostname: "agent-1" }],
  });
  const resource = baseResource({
    item_path: { prefix: "/api/v1/agents", sample_id: "1" },
  });

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  const openButton = await screen.findByTestId(
    "gough-manifest-agents-open-3f2b-aa",
  );
  openButton.click();

  expect(
    await screen.findByTestId("gough-manifest-agents-drawer"),
  ).toBeInTheDocument();
  expect(screen.getByTestId("gough-manifest-agents-facts")).toBeInTheDocument();
});

it("renders no row-open button when the resource declares no item_path", async () => {
  mockProxyRequest.mockResolvedValue({
    agents: [{ agent_id: "3f2b-aa", hostname: "agent-1" }],
  });
  const resource = baseResource({ item_path: null });

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText("agent-1")).toBeInTheDocument());
  expect(
    screen.queryByTestId("gough-manifest-agents-open-3f2b-aa"),
  ).not.toBeInTheDocument();
});

it("renders the create-form open button when the resource declares create", async () => {
  mockProxyRequest.mockResolvedValue({ agents: [] });
  const resource = baseResource({
    create: {
      fields: [
        {
          name: "name",
          label: "Name",
          field_type: "text",
          required: true,
          options: [],
        },
      ],
      submit_label: "Create Agent",
      field_aliases: [],
    },
  });

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  expect(
    await screen.findByTestId("gough-manifest-agents-create"),
  ).toBeInTheDocument();
});

it("retries a failed load from the DataTable's own retry control", async () => {
  mockProxyRequest.mockRejectedValueOnce(new Error("boom"));
  const resource = baseResource();

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestResourceScreen
        productType="gough"
        productLabel="Gough"
        manifest={manifest(resource)}
        resource={resource}
      />
    </QueryClientProvider>,
  );

  const retryButton = await screen.findByRole("button", {
    name: "Retry loading data",
  });
  mockProxyRequest.mockResolvedValueOnce({
    agents: [{ agent_id: "3f2b-aa", hostname: "agent-1" }],
  });
  fireEvent.click(retryButton);

  await waitFor(() => expect(screen.getByText("agent-1")).toBeInTheDocument());
  expect(mockProxyRequest).toHaveBeenCalledTimes(2);
});

/**
 * `RelationshipChildTab` — the child-list fetch + `parent_field` filter a
 * `RelationshipSpec` renders as. Exercised directly (not only through
 * `ManifestResourceDetail`) for fine-grained coverage of the filter's own
 * branches and the no-list fallback.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import {
  RelationshipChildTab,
  matchesRelationshipParent,
} from "../RelationshipChildTab";
import type { ResourceDescriptor } from "../manifestTypes";

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
        sortable: true,
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

function renderTab(childResource: ResourceDescriptor, parentId = "12") {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <RelationshipChildTab
        productType="gough"
        relationship={{ child_kind: "parts", parent_field: "node_id" }}
        childResource={childResource}
        parentId={parentId}
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

describe("matchesRelationshipParent", () => {
  it("matches when the row's own field equals the parent id", () => {
    expect(matchesRelationshipParent({ node_id: "12" }, "node_id", "12")).toBe(
      true,
    );
  });

  it("does not match a different value", () => {
    expect(matchesRelationshipParent({ node_id: "99" }, "node_id", "12")).toBe(
      false,
    );
  });

  it("does not match a null field", () => {
    expect(matchesRelationshipParent({ node_id: null }, "node_id", "12")).toBe(
      false,
    );
  });

  it("does not match a field absent from the row", () => {
    expect(matchesRelationshipParent({}, "node_id", "12")).toBe(false);
  });
});

it("renders the no-list message and never fetches when the child kind has no list endpoint", () => {
  renderTab(partsResource({ list: null }));

  expect(screen.getByTestId("gough-parts-no-list")).toBeInTheDocument();
  expect(screen.getByText(/no list endpoint/)).toBeInTheDocument();
  expect(mockProxyRequest).not.toHaveBeenCalled();
});

it("fetches the child kind's own list and renders only rows matching parent_field, using the child's own columns", async () => {
  mockProxyRequest.mockResolvedValue({
    parts: [
      { id: "p1", name: "Fan", node_id: "12" },
      { id: "p2", name: "Other node's PSU", node_id: "99" },
    ],
  });
  renderTab(partsResource());

  expect(await screen.findByText("Fan")).toBeInTheDocument();
  expect(screen.queryByText("Other node's PSU")).not.toBeInTheDocument();
  expect(mockProxyRequest).toHaveBeenCalledWith(7, "GET", "api/v1/parts/");
});

it("renders the child's own empty_state copy when the fetch returns no matching rows", async () => {
  mockProxyRequest.mockResolvedValue({
    parts: [{ id: "p2", name: "Other node's PSU", node_id: "99" }],
  });
  renderTab(partsResource());

  expect(await screen.findByText("No parts.")).toBeInTheDocument();
});

it("retries through the child's own refetch when the fetch fails", async () => {
  mockProxyRequest.mockRejectedValueOnce(new Error("boom"));
  mockProxyRequest.mockResolvedValueOnce({
    parts: [{ id: "p1", name: "Fan", node_id: "12" }],
  });
  renderTab(partsResource());

  const retryButton = await screen.findByRole("button", {
    name: "Retry loading data",
  });
  fireEvent.click(retryButton);

  await waitFor(() => expect(mockProxyRequest).toHaveBeenCalledTimes(2));
  expect(await screen.findByText("Fan")).toBeInTheDocument();
});

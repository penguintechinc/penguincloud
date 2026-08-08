/**
 * Dashboard Gough card: gating, data sources, and what it refuses to invent.
 *
 * The gating half is the reason this file exists (M9). The card was shipped
 * untested, and its two gates are exactly the kind that read as correct and
 * fail silently: `isProductEnabled` and "does this tenant have a Gough
 * connection". A card that renders for an unconnected tenant shows a row of
 * zeros that says "Gough is here and idle" about a product the tenant does not
 * have.
 *
 * The gate must also stop the FETCHES, not just the markup. A component that
 * returns null after its hooks have already fired still costs an unconnected
 * tenant a round trip per render — a bug only a "the fetch never happens"
 * assertion catches, which is why the query mocks are asserted un-called
 * rather than merely ignored.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
  isProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

const mockNavigate = jest.fn();
jest.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
}));

const goughApi = {
  listNodes: jest.fn(),
  listBiomes: jest.fn(),
  listAgents: jest.fn(),
  createBiome: jest.fn(),
  updateBiome: jest.fn(),
  deleteBiome: jest.fn(),
  updateNodeTags: jest.fn(),
};
jest.mock("../../../api/resources/gough", () => ({ goughApi }));

const goughOperationsApi = {
  listOperations: jest.fn(),
  getOperation: jest.fn(),
  cancelOperation: jest.fn(),
  operationLogs: jest.fn(),
  performAction: jest.fn(),
  metricsSummary: jest.fn(),
};
jest.mock("../../../api/resources/goughOperations", () => ({
  goughOperationsApi,
}));

import GoughSummaryCard from "../GoughSummaryCard";

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <GoughSummaryCard />
    </QueryClientProvider>,
  );
}

const CONNECTED = {
  data: [{ id: 7, product_type: "gough" }],
  isLoading: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue(CONNECTED);
  goughApi.listNodes.mockResolvedValue([
    { id: 12, name: "rack-a-01", state: "ready" },
    { id: 13, name: "rack-a-02", state: "probed" },
  ]);
  goughApi.listAgents.mockResolvedValue([
    { id: 1, agent_id: "3f2b-aa", hostname: "agent-1", status: "active" },
  ]);
  goughOperationsApi.listOperations.mockResolvedValue([]);
  goughOperationsApi.metricsSummary.mockResolvedValue({
    start: "2026-08-08T00:00:00+00:00",
    end: "2026-08-08T00:00:00+00:00",
    series: [],
    totals: {},
  });
});

describe("gating", () => {
  it("renders nothing when the feature flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    const { container } = renderCard();

    expect(container).toBeEmptyDOMElement();
    // The gate must stop the fetch, not just the markup.
    await waitFor(() => expect(goughApi.listNodes).not.toHaveBeenCalled());
    expect(goughOperationsApi.metricsSummary).not.toHaveBeenCalled();
  });

  it("renders nothing when the tenant has no Gough connection", async () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    const { container } = renderCard();

    expect(container).toBeEmptyDOMElement();
    await waitFor(() => expect(goughApi.listNodes).not.toHaveBeenCalled());
    expect(goughOperationsApi.metricsSummary).not.toHaveBeenCalled();
  });

  it("renders nothing when another product is connected but Gough is not", async () => {
    // Selectivity: "has some connection" is not "has a Gough connection".
    mockConnections.mockReturnValue({
      data: [{ id: 9, product_type: "nest" }],
      isLoading: false,
    });

    const { container } = renderCard();

    expect(container).toBeEmptyDOMElement();
    await waitFor(() => expect(goughApi.listNodes).not.toHaveBeenCalled());
  });
});

describe("content", () => {
  it("renders the card for a connected, flagged-on tenant", async () => {
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("gough-summary-card")).toBeInTheDocument(),
    );
  });

  it("counts ready nodes separately from the fleet", async () => {
    renderCard();

    // Two nodes, one of them ready — distinct numbers, so a bug collapsing
    // the two would be visible rather than coincidentally equal.
    await waitFor(() =>
      expect(screen.getByText("Nodes").previousSibling).toHaveTextContent("2"),
    );
    expect(screen.getByText("Ready").previousSibling).toHaveTextContent("1");
  });

  it("reads queue depth from metrics_summary, not from row counts", async () => {
    goughOperationsApi.metricsSummary.mockResolvedValue({
      start: "2026-08-08T00:00:00+00:00",
      end: "2026-08-08T00:00:00+00:00",
      series: [],
      totals: {
        gough_provisioning_queue_depth: 3,
        gough_deployment_queue_depth: 4,
      },
    });

    renderCard();

    await waitFor(() =>
      expect(screen.getByText("Queue depth").previousSibling).toHaveTextContent(
        "7",
      ),
    );
    expect(goughOperationsApi.metricsSummary).toHaveBeenCalledWith(7);
  });

  it("shows a dash rather than a confident zero before metrics land", async () => {
    // A "0" for an unknown value is the same failure the Operation contract
    // refuses for `progress`: an invented number reads as fact.
    renderCard();

    await waitFor(() =>
      expect(screen.getByText("Queue depth").previousSibling).toHaveTextContent(
        "—",
      ),
    );
  });

  it("counts only live operations as running", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([
      { id: "a", kind: "deployment", state: "running", is_terminal: false },
      { id: "b", kind: "deployment", state: "succeeded", is_terminal: true },
    ]);

    renderCard();

    await waitFor(() =>
      expect(screen.getByText("Running ops").previousSibling).toHaveTextContent(
        "1",
      ),
    );
  });

  it("navigates to the fleet on the card action", async () => {
    renderCard();

    const open = await screen.findByTestId("gough-summary-open");
    open.click();

    expect(mockNavigate).toHaveBeenCalledWith("/products/gough/nodes");
  });
});

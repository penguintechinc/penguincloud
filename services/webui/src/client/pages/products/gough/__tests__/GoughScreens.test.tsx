/**
 * Gough screen behaviour: gating, destructive verbs, operation polling.
 *
 * The gates are the point of most of this file. A Gough screen must render
 * nothing product-shaped when the feature flag is off OR the tenant has no
 * Gough connection, and both conditions live in one shared shell precisely so
 * a fourth screen cannot ship with one of them missing. A test per screen is
 * what keeps that true.
 *
 * The destructive verbs are the other half: `deploy`, `evacuate` and `reject`
 * commission, drain and remove physical hardware. None may fire from a single
 * click — each goes through a ConfirmDialog first.
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../../lib/featureGates", () => ({
  isProductEnabled: (key: string) => mockIsProductEnabled(key),
  // Components read the reactive form; the sidebar builder still reads the
  // sync one. Both are mocked to the same answer so a test cannot pass
  // against one gate while the component consults the other.
  useProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
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
jest.mock("../../../../api/resources/gough", () => ({ goughApi }));

const goughOperationsApi = {
  listOperations: jest.fn(),
  getOperation: jest.fn(),
  cancelOperation: jest.fn(),
  operationLogs: jest.fn(),
  // I5: node and agent verbs go through the TYPED route now, so the pages
  // call performAction rather than the proxy bindings in `gough.ts`.
  performAction: jest.fn(),
};
jest.mock("../../../../api/resources/goughOperations", () => ({
  goughOperationsApi,
}));

import NodesPage from "../NodesPage";
import BiomesPage from "../BiomesPage";
import AgentsPage from "../AgentsPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
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
    { id: 12, name: "rack-a-01", state: "ready", posture: "compliant" },
  ]);
  goughApi.listBiomes.mockResolvedValue([
    { id: 4, name: "web", is_active: true, biome_kind: "custom" },
  ]);
  goughApi.listAgents.mockResolvedValue([
    { id: 1, agent_id: "3f2b-aa", hostname: "agent-1", status: "active" },
  ]);
  goughOperationsApi.listOperations.mockResolvedValue([]);
});

describe("gating", () => {
  it.each([
    ["nodes", <NodesPage key="n" />],
    ["biomes", <BiomesPage key="b" />],
    ["agents", <AgentsPage key="a" />],
  ])(
    "renders nothing product-shaped for %s when the flag is off",
    async (_name, element) => {
      mockIsProductEnabled.mockReturnValue(false);

      renderPage(element);

      expect(screen.getByTestId("gough-disabled")).toBeInTheDocument();
      expect(screen.queryByTestId("gough-screen")).not.toBeInTheDocument();
      // The flag is a navigation gate, not a data gate, but a screen that
      // fetched anyway would still leak the fleet into the cache.
      expect(goughApi.listNodes).not.toHaveBeenCalled();
    },
  );

  it("renders an empty state when the tenant has no Gough connection", async () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<NodesPage />);

    expect(screen.getByTestId("gough-no-connection")).toBeInTheDocument();
    expect(goughApi.listNodes).not.toHaveBeenCalled();
  });

  it("shows a placeholder while the connection list is loading", () => {
    mockConnections.mockReturnValue({ data: undefined, isLoading: true });
    renderPage(<NodesPage />);
    expect(screen.getByTestId("gough-loading")).toBeInTheDocument();
  });

  it("ignores a connection to a different product", async () => {
    mockConnections.mockReturnValue({
      data: [{ id: 9, product_type: "nest" }],
      isLoading: false,
    });

    renderPage(<NodesPage />);

    expect(screen.getByTestId("gough-no-connection")).toBeInTheDocument();
  });
});

describe("NodesPage", () => {
  it("lists nodes and opens the drawer", async () => {
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-node-open-12")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("gough-node-open-12"));
    expect(screen.getByTestId("gough-node-drawer")).toBeInTheDocument();
    // Scoped to the drawer: the table renders these words too, and an
    // unscoped query would pass even if the drawer showed nothing.
    const facts = within(screen.getByTestId("gough-facts"));
    // State and posture are both shown: a node can be ready and non-compliant.
    expect(facts.getByText("ready")).toBeInTheDocument();
    expect(facts.getByText("compliant")).toBeInTheDocument();
  });

  it.each(["deploy", "evacuate", "reject"])(
    "requires confirmation before %s reaches the product",
    async (verb) => {
      goughOperationsApi.performAction.mockResolvedValue({
        action: verb,
        accepted: true,
        operations: [],
      });
      renderPage(<NodesPage />);

      await waitFor(() =>
        expect(screen.getByTestId("gough-node-open-12")).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByTestId("gough-node-open-12"));
      fireEvent.click(screen.getByTestId(`gough-node-action-${verb}`));

      // The dialog is up and nothing has been sent yet.
      expect(screen.getByTestId("gough-node-confirm")).toBeInTheDocument();
      expect(goughOperationsApi.performAction).not.toHaveBeenCalled();

      fireEvent.click(screen.getByTestId("gough-node-confirm-confirm"));

      await waitFor(() =>
        expect(goughOperationsApi.performAction).toHaveBeenCalledWith(
          7,
          "nodes",
          "12",
          verb,
        ),
      );
    },
  );

  it("does not act when the confirmation is dismissed", async () => {
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-node-open-12")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-node-open-12"));
    fireEvent.click(screen.getByTestId("gough-node-action-reject"));
    fireEvent.click(screen.getByTestId("gough-node-confirm-cancel"));

    expect(goughOperationsApi.performAction).not.toHaveBeenCalled();
  });
});

describe("BiomesPage", () => {
  it("deletes a biome only after confirmation", async () => {
    goughApi.deleteBiome.mockResolvedValue({});
    renderPage(<BiomesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-biome-open-4")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-biome-open-4"));
    fireEvent.click(screen.getByTestId("gough-biome-delete"));

    expect(goughApi.deleteBiome).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("gough-biome-confirm-confirm"));

    await waitFor(() =>
      expect(goughApi.deleteBiome).toHaveBeenCalledWith(7, "4"),
    );
  });
});

describe("AgentsPage", () => {
  it("addresses an agent by agent_id, never the row id", async () => {
    goughOperationsApi.performAction.mockResolvedValue({
      action: "suspend",
      accepted: true,
      operations: [],
    });
    renderPage(<AgentsPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-agent-open-3f2b-aa"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-agent-open-3f2b-aa"));
    fireEvent.click(screen.getByTestId("gough-agent-suspend"));
    fireEvent.click(screen.getByTestId("gough-agent-confirm-confirm"));

    await waitFor(() =>
      expect(goughOperationsApi.performAction).toHaveBeenCalledWith(
        7,
        "agents",
        "3f2b-aa",
        "suspend",
      ),
    );
  });
});

describe("operations panel", () => {
  it("stays hidden when nothing is running", async () => {
    renderPage(<NodesPage />);
    await waitFor(() =>
      expect(screen.getByTestId("gough-node-open-12")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("gough-operations")).not.toBeInTheDocument();
  });

  it("shows a live operation with a cancel control and a real progress bar", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([
      {
        id: "op-1",
        kind: "biome_upgrade",
        state: "running",
        status: "in_progress",
        is_terminal: false,
        progress: 0.5,
      },
    ]);

    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-operations")).toBeInTheDocument(),
    );
    expect(screen.getByText("in_progress")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(
      screen.getByTestId("gough-operation-cancel-op-1"),
    ).toBeInTheDocument();
  });

  it("offers no cancel for a terminal operation and invents no progress", async () => {
    // A Gough deployment reports only an unbounded `phase`, so progress is
    // null and no bar may be drawn from it.
    goughOperationsApi.listOperations.mockResolvedValue([
      {
        id: "op-2",
        kind: "deployment",
        state: "succeeded",
        status: "succeeded",
        is_terminal: true,
        progress: null,
      },
    ]);

    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-operations")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("gough-operation-cancel-op-2"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("cancels a live operation", async () => {
    goughOperationsApi.listOperations.mockResolvedValue([
      {
        id: "op-1",
        kind: "deployment",
        state: "running",
        status: "in_progress",
        is_terminal: false,
      },
    ]);
    goughOperationsApi.cancelOperation.mockResolvedValue({});

    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-cancel-op-1"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-operation-cancel-op-1"));

    await waitFor(() =>
      expect(goughOperationsApi.cancelOperation).toHaveBeenCalledWith(
        7,
        "deployment",
        "op-1",
      ),
    );
  });
});

describe("operation logs (M15)", () => {
  /**
   * The jobs-log surface. `operationLogs` on the API client and
   * `operation_logs` on the adapter were implemented and tested but had no
   * caller — the brief's DetailDrawer log tab was never built. These tests
   * cover the tab that makes that chain reachable.
   */
  beforeEach(() => {
    goughOperationsApi.listOperations.mockResolvedValue([
      {
        id: "dep-1",
        kind: "deployment",
        state: "running",
        status: "in_progress",
        is_terminal: false,
      },
    ]);
  });

  it("does not fetch logs until the operator opens them", async () => {
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("gough-operation-dep-1")).toBeInTheDocument(),
    );
    // A panel listing ten deployments must not fetch ten log streams nobody
    // asked for — the `enabled` flag is what makes the disclosure cheap.
    expect(goughOperationsApi.operationLogs).not.toHaveBeenCalled();
  });

  it("fetches and renders log lines once opened", async () => {
    goughOperationsApi.operationLogs.mockResolvedValue([
      { timestamp: "2026-08-08T00:00:00Z", level: "info", message: "started" },
      { timestamp: "2026-08-08T00:00:05Z", level: "error", message: "boom" },
    ]);
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-logs-toggle-dep-1"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-operation-logs-toggle-dep-1"));

    await waitFor(() =>
      expect(screen.getByText("started")).toBeInTheDocument(),
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(goughOperationsApi.operationLogs).toHaveBeenCalledWith(
      7,
      "deployment",
      "dep-1",
    );
  });

  it("reports an empty stream rather than rendering nothing", async () => {
    goughOperationsApi.operationLogs.mockResolvedValue([]);
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-logs-toggle-dep-1"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-operation-logs-toggle-dep-1"));

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-logs-empty-dep-1"),
      ).toBeInTheDocument(),
    );
  });

  it("surfaces a log fetch failure instead of showing an empty stream", async () => {
    // An error rendered as "no log lines yet" tells an operator the deploy is
    // quiet when in fact the portal could not read it.
    goughOperationsApi.operationLogs.mockRejectedValue(new Error("nope"));
    renderPage(<NodesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-logs-toggle-dep-1"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("gough-operation-logs-toggle-dep-1"));

    await waitFor(() =>
      expect(
        screen.getByTestId("gough-operation-logs-error-dep-1"),
      ).toBeInTheDocument(),
    );
  });

  it("exposes the disclosure state to assistive tech", async () => {
    renderPage(<NodesPage />);

    const toggle = await screen.findByTestId(
      "gough-operation-logs-toggle-dep-1",
    );
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

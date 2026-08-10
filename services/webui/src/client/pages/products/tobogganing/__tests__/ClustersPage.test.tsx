/**
 * Tobogganing SD-WAN Clusters screen.
 *
 * The gating block is repeated on every Tobogganing screen rather than
 * factored into a shared helper. That is deliberate: the gate is per-component
 * — a screen that forgot to thread `isEnabled` into its query would still pass
 * a helper's assertions run against a different screen, which is precisely the
 * "test agrees with the bug by construction" shape this phase exists to end.
 * Each screen proves its OWN fetch is gated.
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

const tobogganingApi = { listClusters: jest.fn() };
jest.mock("../../../../api/resources/tobogganing", () => ({ tobogganingApi }));

import ClustersPage from "../ClustersPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const CLUSTER = {
  id: "cluster-a",
  name: "us-east",
  region: "us-east-1",
  datacenter: "dal2",
  status: "active",
  client_count: 12,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "tobogganing" }],
    isLoading: false,
  });
  tobogganingApi.listClusters.mockResolvedValue([CLUSTER]);
});

describe("gating", () => {
  it("does not fetch when the flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<ClustersPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
    expect(tobogganingApi.listClusters).not.toHaveBeenCalled();
  });

  it("does not fetch with no Tobogganing connection", () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<ClustersPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listClusters).not.toHaveBeenCalled();
  });
});

describe("the cluster list", () => {
  it("renders the rows the product returned", async () => {
    renderPage(<ClustersPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("us-east")).toBeInTheDocument();
    expect(table.getByText("us-east-1")).toBeInTheDocument();
    expect(table.getByText("dal2")).toBeInTheDocument();
    expect(table.getByText("12")).toBeInTheDocument();
  });

  it("renders a client count of zero as zero, not as a dash", async () => {
    // An empty cluster is exactly what an operator looks for when a rollout
    // has not landed. Rendering 0 as "—" would say the product reported no
    // count at all, which is a different and false statement.
    tobogganingApi.listClusters.mockResolvedValue([
      { ...CLUSTER, client_count: 0 },
    ]);

    renderPage(<ClustersPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("0")).toBeInTheDocument();
    expect(table.queryByText("—")).not.toBeInTheDocument();
  });

  it("renders an absent client count as a dash", async () => {
    tobogganingApi.listClusters.mockResolvedValue([
      { ...CLUSTER, client_count: null },
    ]);

    renderPage(<ClustersPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("—")).toBeInTheDocument();
  });

  it("surfaces a decode failure instead of reporting no clusters", async () => {
    tobogganingApi.listClusters.mockRejectedValue(
      new Error('no "clusters" key (got ["items"]) — refusing to report empty'),
    );

    renderPage(<ClustersPage />);

    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText(/refusing to report empty/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("opens a drawer with the facts for one cluster", async () => {
    renderPage(<ClustersPage />);

    fireEvent.click(
      await screen.findByTestId("tobogganing-cluster-open-cluster-a"),
    );

    const facts = within(screen.getByTestId("tobogganing-facts"));
    expect(facts.getByText("us-east-1")).toBeInTheDocument();
    expect(facts.getByText("12")).toBeInTheDocument();
  });
});

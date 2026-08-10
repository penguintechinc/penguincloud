/**
 * Tobogganing SD-WAN Clients screen: gating, decoding, absence of writes.
 *
 * The gates are the point of the first block. A Tobogganing screen must render
 * nothing product-shaped when the feature flag is off OR the tenant has no
 * Tobogganing connection — and, separately, must not FETCH in either case.
 * Those are two different assertions because they fail independently: hooks run
 * before a component decides what to render, so a screen showing a "disabled"
 * placeholder can already have pulled the tenant's fleet into the cache and
 * spent the product credential doing it. The Gough phase shipped exactly that.
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

const tobogganingApi = {
  listClients: jest.fn(),
  listClusters: jest.fn(),
  listPeers: jest.fn(),
  listBlockPages: jest.fn(),
  listSwgPolicies: jest.fn(),
};
jest.mock("../../../../api/resources/tobogganing", () => ({ tobogganingApi }));

import ClientsPage from "../ClientsPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const CONNECTED = {
  data: [{ id: 7, product_type: "tobogganing" }],
  isLoading: false,
};

const CLIENT = {
  id: "client-1",
  name: "branch-nyc",
  type: "docker",
  cluster_id: "cluster-a",
  status: "active",
  last_seen: "2026-08-09T01:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue(CONNECTED);
  tobogganingApi.listClients.mockResolvedValue([CLIENT]);
});

describe("gating", () => {
  it("renders nothing product-shaped when the flag is off", () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<ClientsPage />);

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
    expect(screen.queryByTestId("tobogganing-screen")).not.toBeInTheDocument();
  });

  it("does not fetch when the flag is off", async () => {
    // The flag gates the FETCH, not only the render. A screen that returned
    // the "disabled" placeholder while its query still ran would have pulled
    // the tenant's fleet into the cache and spent the product credential
    // doing it — which is the Gough defect, not a theoretical one.
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<ClientsPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(tobogganingApi.listClients).not.toHaveBeenCalled();
  });

  it("gates on the tobogganing key specifically", () => {
    // A screen gated on the wrong product key would be enabled by another
    // product's flag — invisible while both are off, which is the default.
    mockIsProductEnabled.mockImplementation((key) => key !== "tobogganing");

    renderPage(<ClientsPage />);

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
  });

  it("renders an empty state and does not fetch with no connection", () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<ClientsPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listClients).not.toHaveBeenCalled();
  });

  it("shows a placeholder while the connection list is loading", () => {
    mockConnections.mockReturnValue({ data: undefined, isLoading: true });

    renderPage(<ClientsPage />);

    expect(screen.getByTestId("tobogganing-loading")).toBeInTheDocument();
  });

  it("ignores a connection to a different product", () => {
    mockConnections.mockReturnValue({
      data: [{ id: 9, product_type: "nest" }],
      isLoading: false,
    });

    renderPage(<ClientsPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listClients).not.toHaveBeenCalled();
  });
});

describe("the client list", () => {
  it("renders the rows the product returned", async () => {
    renderPage(<ClientsPage />);

    // Scoped to the table: the name also appears on the row-open button, and
    // an unscoped getByText would pass on either one alone.
    const table = within(await screen.findByRole("table"));
    expect(table.getByText("branch-nyc")).toBeInTheDocument();
    expect(table.getByText("docker")).toBeInTheDocument();
    expect(table.getByText("cluster-a")).toBeInTheDocument();
    expect(table.getByText("active")).toBeInTheDocument();
    expect(tobogganingApi.listClients).toHaveBeenCalledWith(7);
  });

  it("shows an unassigned cluster as a dash, not a blank cell", async () => {
    // An enrolled client with no cluster is a real state an operator opens
    // this page to find. A blank cell reads as a layout fault instead.
    tobogganingApi.listClients.mockResolvedValue([
      { ...CLIENT, cluster_id: null },
    ]);

    renderPage(<ClientsPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("—")).toBeInTheDocument();
    expect(table.queryByText("cluster-a")).not.toBeInTheDocument();
  });

  it("surfaces a decode failure instead of reporting an empty fleet", async () => {
    // `envelopeList` throws when the `clients` key is absent. The screen must
    // show that as an error — rendering "no clients" would tell the operator
    // their fabric is empty when the truth is that the response was not the
    // shape this client understands.
    tobogganingApi.listClients.mockRejectedValue(
      new Error('no "clients" key (got ["items"]) — refusing to report empty'),
    );

    renderPage(<ClientsPage />);

    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText("Error loading data")).toBeInTheDocument();
    expect(alert.getByText(/refusing to report empty/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("opens a drawer with the facts for one client", async () => {
    renderPage(<ClientsPage />);

    fireEvent.click(
      await screen.findByTestId("tobogganing-client-open-client-1"),
    );

    expect(screen.getByTestId("tobogganing-client-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("tobogganing-facts")).toHaveTextContent("active");
  });

  it("offers no create, rotate or delete verb", async () => {
    // Not an oversight. Every mutating client route is refused by the proxy
    // allowlist: create and rotate-key return a freshly minted api_key in the
    // response body, and tunnel-config/config authenticate the client's own
    // key inline rather than the portal credential.
    renderPage(<ClientsPage />);
    await screen.findByRole("table");

    expect(screen.queryByRole("button", { name: /new|create/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /rotate/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });
});

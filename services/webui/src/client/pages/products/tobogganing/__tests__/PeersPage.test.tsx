/**
 * Tobogganing WireGuard Peers screen.
 *
 * Two things are specific to this screen and neither is visible by reading it:
 *
 * 1. **A peer has no `id`.** The product returns `node_id`, `public_key` and
 *    `ip_address` and nothing else, so the row id is derived from `node_id`.
 *    Keying on the absent `id` gives every row the key `"undefined"` — which
 *    is TRUTHY, so `DataTable`'s `row.id || idx` fallback does not rescue it
 *    and all rows collide on one key. The rows still render, which is why the
 *    obvious row-count assertion does NOT catch this; the symptom is a React
 *    duplicate-key warning and unstable reconciliation on sort or refetch.
 *    That warning is therefore what is asserted, having first confirmed by
 *    injection that a row-count assertion stays green against the bug.
 * 2. **The path is the SD-WAN one.** `/api/v1/wireguard/peers` is the machine
 *    plane and is one segment away; that pair is asserted in the api tests and
 *    in `test_tobogganing_webui_paths.py`.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../../lib/featureGates", () => ({
  isProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

const tobogganingApi = { listPeers: jest.fn() };
jest.mock("../../../../api/resources/tobogganing", () => ({ tobogganingApi }));

import PeersPage from "../PeersPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const PEER = {
  node_id: "headend-1",
  public_key: "kZ9lQ3rTn8xWv2bYc5dFg7hJk1mNp4qRs6tUv8wXyZ0=",
  ip_address: "10.200.0.4",
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "tobogganing" }],
    isLoading: false,
  });
  tobogganingApi.listPeers.mockResolvedValue([PEER]);
});

describe("gating", () => {
  it("does not fetch when the flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<PeersPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
    expect(tobogganingApi.listPeers).not.toHaveBeenCalled();
  });

  it("does not fetch with no Tobogganing connection", () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<PeersPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listPeers).not.toHaveBeenCalled();
  });
});

describe("the peer list", () => {
  it("renders every peer the product returned", async () => {
    tobogganingApi.listPeers.mockResolvedValue([
      PEER,
      { ...PEER, node_id: "headend-2", ip_address: "10.200.0.5" },
      { ...PEER, node_id: "client-9", ip_address: "10.200.0.6" },
    ]);

    renderPage(<PeersPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getAllByRole("row")).toHaveLength(4); // header + 3
    expect(table.getByText("headend-1")).toBeInTheDocument();
    expect(table.getByText("headend-2")).toBeInTheDocument();
    expect(table.getByText("client-9")).toBeInTheDocument();
    expect(screen.getByTestId("tobogganing-peer-count")).toHaveTextContent(
      "3 peers",
    );
  });

  it("gives each row a distinct key, derived from node_id", async () => {
    // A peer carries no `id`. Reading one yields `String(undefined)` ===
    // "undefined", which is truthy — so `DataTable`'s `row.id || idx` fallback
    // does NOT kick in and every row collides on a single key.
    //
    // The rows still render, so the test above stays green against that bug;
    // that was verified by injection, not assumed. React's duplicate-key
    // warning is the actual symptom, so it is the actual assertion.
    const errors = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    tobogganingApi.listPeers.mockResolvedValue([
      PEER,
      { ...PEER, node_id: "headend-2" },
    ]);

    renderPage(<PeersPage />);
    await screen.findByRole("table");

    const messages = errors.mock.calls.map((call) => String(call[0]));
    expect(messages.filter((m) => /same key|unique "key"/i.test(m))).toEqual(
      [],
    );
    errors.mockRestore();
  });

  it("shows the public key in full rather than truncating it", async () => {
    // A silently shortened base64 key is worse than a long one: an operator
    // comparing it against a node's config would read a match that is not
    // there.
    renderPage(<PeersPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText(PEER.public_key)).toBeInTheDocument();
  });

  it("reports a genuinely empty fabric as empty", async () => {
    tobogganingApi.listPeers.mockResolvedValue([]);

    renderPage(<PeersPage />);

    expect(
      await screen.findByTestId("tobogganing-peers-empty"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tobogganing-peer-count")).toHaveTextContent(
      "0 peers",
    );
  });

  it("shows no count while the fetch is still in flight", async () => {
    // "0 peers" rendered during loading is a fact stated wrongly, and it is
    // the same failure mode as decoding an absent envelope key as empty.
    let resolve: (rows: unknown[]) => void = () => {};
    tobogganingApi.listPeers.mockReturnValue(
      new Promise((r) => {
        resolve = r as (rows: unknown[]) => void;
      }),
    );

    renderPage(<PeersPage />);

    expect(screen.queryByTestId("tobogganing-peer-count")).toBeNull();
    resolve([PEER]);
    await screen.findByRole("table");
    expect(screen.getByTestId("tobogganing-peer-count")).toHaveTextContent(
      "1 peer",
    );
  });

  it("surfaces a decode failure instead of reporting no peers", async () => {
    tobogganingApi.listPeers.mockRejectedValue(
      new Error('no "peers" key (got ["items"]) — refusing to report empty'),
    );

    renderPage(<PeersPage />);

    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText(/refusing to report empty/)).toBeInTheDocument();
    expect(screen.queryByTestId("tobogganing-peers-empty")).toBeNull();
    expect(screen.queryByTestId("tobogganing-peer-count")).toBeNull();
  });
});

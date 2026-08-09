/**
 * Nest Billing screen: gating, and the difference between "no data" and
 * "no cost service".
 *
 * That distinction is the reason most of this file exists. Nest's cost routes
 * proxy to `nest-cost-calculator` and answer 503 when it is not deployed. If
 * the screen rendered that as an empty table it would tell an operator they
 * were billed nothing — a claim about their account, rather than about the
 * deployment. The two paths are asserted separately here so one cannot quietly
 * start rendering as the other.
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

const nestApi = {
  listDatabases: jest.fn(),
  listSnapshots: jest.fn(),
  costReport: jest.fn(),
  costSummary: jest.fn(),
};
jest.mock("../../../../api/resources/nest", () => ({ nestApi }));

import BillingPage from "../BillingPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const CONNECTED = { data: [{ id: 7, product_type: "nest" }], isLoading: false };

const RECORDS = [
  {
    month: "2026-07",
    totalTokens: 1250,
    totalCostUsd: 42.5,
    breakdown: { postgres: 1000, object: 250 },
    updatedAt: "2026-08-01T00:00:00Z",
  },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue(CONNECTED);
  nestApi.costReport.mockResolvedValue({
    available: true,
    data: { records: RECORDS },
  });
  nestApi.costSummary.mockResolvedValue({
    available: true,
    data: { totalTokens: 1250, totalCostUsd: 42.5, months: 1 },
  });
});

describe("gating", () => {
  it("renders nothing product-shaped when the flag is off", () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<BillingPage />);

    expect(screen.getByTestId("nest-disabled")).toBeInTheDocument();
  });

  it("does not fetch cost data when the flag is off", async () => {
    // Cost data is commercially sensitive and the fetch spends the product
    // credential; a render-only gate would do both anyway.
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<BillingPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(nestApi.costReport).not.toHaveBeenCalled();
    expect(nestApi.costSummary).not.toHaveBeenCalled();
  });

  it("does not fetch when the tenant has no Nest connection", async () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<BillingPage />);

    expect(screen.getByTestId("nest-no-connection")).toBeInTheDocument();
    expect(nestApi.costReport).not.toHaveBeenCalled();
  });
});

describe("cost reporting", () => {
  it("lists metered months with their cost", async () => {
    renderPage(<BillingPage />);

    // Scoped to the table: the month and the token count also appear in the
    // summary tiles and the per-type breakdown, so an unscoped query would
    // pass even if the table rendered nothing.
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    const table = within(screen.getByRole("table"));
    expect(table.getByText("2026-07")).toBeInTheDocument();
    expect(table.getByText("42.50")).toBeInTheDocument();
    expect(table.getByText("1,250")).toBeInTheDocument();
  });

  it("reads totals from the product's summary, not from the visible rows", async () => {
    // The table holds what this request returned, which is not guaranteed to
    // be every month the calculator has — summing it would render a partial
    // figure as a total.
    nestApi.costSummary.mockResolvedValue({
      available: true,
      data: { totalTokens: 99999, totalCostUsd: 1234.5, months: 12 },
    });

    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(screen.getByTestId("nest-billing-summary")).toBeInTheDocument(),
    );
    expect(screen.getByText("1234.50")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("breaks usage down per resource type", async () => {
    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-usage-breakdown-2026-07"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("postgres")).toBeInTheDocument();
    expect(screen.getByText("object")).toBeInTheDocument();
  });
});

describe("degraded states", () => {
  it("says the cost service is absent rather than showing an empty table", async () => {
    // Session 1 flagged this: Nest answers 503 when nest-cost-calculator is
    // not deployed. An empty table would read as "you were billed nothing".
    nestApi.costReport.mockResolvedValue({ available: false, data: null });
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-billing-unavailable"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("nest-billing-summary")).toBeNull();
  });

  it("distinguishes a metered tenant with no months from an absent service", async () => {
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: { records: [] },
    });

    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(
        screen.queryByTestId("nest-billing-unavailable"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId("nest-usage-breakdown")).toBeNull();
  });

  it("does not render an absent total as zero", async () => {
    // "0.00" is a statement about the bill; a missing figure is not one.
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-billing-summary-absent"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("0.00")).toBeNull();
  });

  it("surfaces a real failure instead of the not-deployed notice", async () => {
    // Only 503 means "no calculator". Anything else is an auth or routing
    // fault and must not be reported as a deployment choice.
    nestApi.costReport.mockRejectedValue(new Error("boom"));

    renderPage(<BillingPage />);

    await waitFor(() =>
      expect(
        screen.queryByTestId("nest-billing-unavailable"),
      ).not.toBeInTheDocument(),
    );
  });
});

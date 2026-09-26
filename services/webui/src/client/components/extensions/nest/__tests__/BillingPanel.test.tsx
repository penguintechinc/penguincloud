/**
 * Nest's Billing `page`-slot panel — the tri-state availability contract
 * `BillingPage.tsx`'s own doc names (available / empty / error) must survive
 * the move to `ExtensionPageProps`, plus the aggregate KPI tiles and the
 * open-map per-month breakdown.
 *
 * Unlike `BillingPage.test.tsx`, there is no flag/connection gating to mock
 * here: `productId`/`tenantId` arrive as already-resolved props, matching
 * what `ExtensionSlotRenderer` actually hands a registered extension.
 */
import {
  render,
  screen,
  waitFor,
  within,
  fireEvent,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { ExtensionSlot } from "../../../kit/manifestTypes";

const nestApi = {
  costReport: jest.fn(),
  costSummary: jest.fn(),
};
jest.mock("../../../../api/resources/nest", () => ({ nestApi }));

import BillingPanel from "../BillingPanel";

const SLOT: ExtensionSlot = {
  slot: "page",
  id: "billing",
  label: "Billing",
  resource: null,
  position: 0,
};

function renderPanel(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

function panel() {
  return (
    <BillingPanel productType="nest" productId={7} tenantId={42} slot={SLOT} />
  );
}

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
  nestApi.costReport.mockResolvedValue({
    available: true,
    data: { records: RECORDS },
  });
  nestApi.costSummary.mockResolvedValue({
    available: true,
    data: { totalTokens: 1250, totalCostUsd: 42.5, months: 1 },
  });
});

describe("cost reporting", () => {
  it("fetches both endpoints with productId/tenantId taken from props", async () => {
    renderPanel(panel());

    await waitFor(() => expect(nestApi.costReport).toHaveBeenCalledWith(7));
    expect(nestApi.costSummary).toHaveBeenCalledWith(7);
  });

  it("lists metered months with their cost", async () => {
    renderPanel(panel());

    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    const table = within(screen.getByRole("table"));
    expect(table.getByText("2026-07")).toBeInTheDocument();
    expect(table.getByText("42.50")).toBeInTheDocument();
    expect(table.getByText("1,250")).toBeInTheDocument();
  });

  it("reads totals from the product's summary, not from the visible rows", async () => {
    nestApi.costSummary.mockResolvedValue({
      available: true,
      data: { totalTokens: 99999, totalCostUsd: 1234.5, months: 12 },
    });

    renderPanel(panel());

    await waitFor(() =>
      expect(screen.getByTestId("nest-billing-summary")).toBeInTheDocument(),
    );
    expect(screen.getByText("1234.50")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("breaks usage down per resource type", async () => {
    renderPanel(panel());

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-usage-breakdown-2026-07"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("postgres")).toBeInTheDocument();
    expect(screen.getByText("object")).toBeInTheDocument();
  });

  it("dashes every summary tile whose figure the product did not report", async () => {
    nestApi.costSummary.mockResolvedValue({
      available: true,
      data: { totalTokens: null, totalCostUsd: null, months: null },
    });

    renderPanel(panel());

    const summary = within(await screen.findByTestId("nest-billing-summary"));
    expect(summary.getAllByText("—")).toHaveLength(3);
  });

  it("stringifies a non-numeric breakdown figure rather than dropping it", async () => {
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: {
        records: [{ month: "2026-09", breakdown: { note: "manual entry" } }],
      },
    });

    renderPanel(panel());

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-usage-breakdown-2026-09"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("manual entry")).toBeInTheDocument();
  });

  it("shows the summary loading placeholder before the summary query settles", () => {
    nestApi.costSummary.mockReturnValue(new Promise(() => {}));

    renderPanel(panel());

    expect(
      screen.getByTestId("nest-billing-summary-loading"),
    ).toBeInTheDocument();
  });
});

describe("degraded states", () => {
  it("says the cost service is absent rather than showing an empty table", async () => {
    nestApi.costReport.mockResolvedValue({ available: false, data: null });
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    renderPanel(panel());

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

    renderPanel(panel());

    await waitFor(() =>
      expect(
        screen.queryByTestId("nest-billing-unavailable"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId("nest-usage-breakdown")).toBeNull();
  });

  it("does not render an absent total as zero", async () => {
    nestApi.costSummary.mockResolvedValue({ available: false, data: null });

    renderPanel(panel());

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-billing-summary-absent"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("0.00")).toBeNull();
  });

  it("surfaces a real failure instead of the not-deployed notice", async () => {
    nestApi.costReport.mockRejectedValue(new Error("boom"));

    renderPanel(panel());

    await waitFor(() =>
      expect(
        screen.queryByTestId("nest-billing-unavailable"),
      ).not.toBeInTheDocument(),
    );
  });

  it("retries the cost-report fetch when the table's Retry control is used", async () => {
    // A real failure with no prior data takes the DataTable's full-page
    // error branch, which is the only branch that renders `onRetry` as a
    // clickable control.
    nestApi.costReport.mockRejectedValueOnce(new Error("boom"));

    renderPanel(panel());

    const retry = await screen.findByRole("button", {
      name: "Retry loading data",
    });
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: { records: RECORDS },
    });
    fireEvent.click(retry);

    await waitFor(() => expect(nestApi.costReport).toHaveBeenCalledTimes(2));
  });

  it("renders absent cells for a row missing tokens/cost/breakdown/updatedAt", async () => {
    nestApi.costReport.mockResolvedValue({
      available: true,
      data: { records: [{ month: "2026-08" }] },
    });

    renderPanel(panel());

    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    const table = within(screen.getByRole("table"));
    expect(table.getAllByText("—").length).toBeGreaterThan(0);
  });
});

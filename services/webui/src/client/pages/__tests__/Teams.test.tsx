/**
 * Teams page: a failed `/teams` load must render visibly, and must not read
 * the same as a tenant that genuinely has zero teams.
 *
 * Before this fix, the page derived its own `teams.length === 0` empty
 * state and never looked at `teamsQuery.error` — a rejected request and a
 * genuinely empty tenant both landed on "No teams yet." The regression
 * tests below are written to fail against that shape (see the injection
 * note on the first one) and pass against the fixed one, which wires
 * `error`/`isLoading` into `DataTable` and gates the custom empty state on
 * `!error`, matching the pattern every Gough/Nest/Tobogganing list screen
 * already uses (e.g. `pages/products/tobogganing/PeersPage.tsx`).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { createAppQueryClient } from "../../lib/queryClient";

jest.mock("../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({
      currentTenant: { id: 42, name: "Acme", display_name: "Acme Corp" },
    }),
}));

const api = { get: jest.fn() };
jest.mock("../../lib/api", () => ({ __esModule: true, default: api }));

import Teams from "../Teams";

function renderPage(element: ReactElement) {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const TEAM = {
  id: "t-1",
  name: "Platform",
  slug: "platform",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("a healthy load", () => {
  it("renders every team the tenant has", async () => {
    api.get.mockResolvedValue({ data: { teams: [TEAM] } });

    renderPage(<Teams />);

    expect(await screen.findByText("Platform")).toBeInTheDocument();
    expect(screen.queryByTestId("teams-empty")).not.toBeInTheDocument();
  });

  it("reports a genuinely empty tenant as empty, not as an error", async () => {
    api.get.mockResolvedValue({ data: { teams: [] } });

    renderPage(<Teams />);

    expect(await screen.findByTestId("teams-empty")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("a failed load", () => {
  it("surfaces a failed team list instead of reporting no teams", async () => {
    // Injection proof: with the `!error` gate removed from Teams.tsx (i.e.
    // reverting to `teams.length === 0 ? <empty div> : <DataTable .../>`
    // with no `error` prop passed to DataTable at all), this assertion
    // fails — `findByRole("alert")` times out because the page renders "No
    // teams yet" instead. Verified by temporarily reverting the fix locally
    // and re-running this test; see the task report for the captured
    // failure output.
    api.get.mockRejectedValue({
      isAxiosError: true,
      response: { data: { error: "Insufficient permissions" } },
    });

    renderPage(<Teams />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Insufficient permissions");
    expect(screen.queryByTestId("teams-empty")).not.toBeInTheDocument();
    expect(screen.queryByText(/No teams yet/i)).not.toBeInTheDocument();
  });

  it("does not render the raw body of an upstream-marked failure", async () => {
    // Same provenance rule the mutation-error banner enforces
    // (`lib/mutationError.ts`): a response the proxy marked
    // `X-Portal-Upstream-Response` is untrusted product text and must never
    // reach the DOM verbatim, regardless of what it contains.
    api.get.mockRejectedValue({
      isAxiosError: true,
      response: {
        data: { error: "internal: teams-svc.portal.svc.cluster.local:5432" },
        headers: { "x-portal-upstream-response": "1" },
      },
    });

    renderPage(<Teams />);

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("teams-svc.portal.svc.cluster.local");
    expect(alert).toHaveTextContent(/could not be loaded/i);
  });

  it("clears the error and shows data once the query recovers", async () => {
    api.get.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { error: "Insufficient permissions" } },
    });
    api.get.mockResolvedValueOnce({ data: { teams: [TEAM] } });

    renderPage(<Teams />);

    const retry = await screen.findByRole("button", { name: /retry/i });
    retry.click();

    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Platform")).toBeInTheDocument();
  });
});

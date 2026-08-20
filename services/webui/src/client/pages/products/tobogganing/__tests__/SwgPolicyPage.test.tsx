/**
 * Tobogganing SASE SWG Policy screen.
 *
 * Two product behaviours drive everything here and neither is visible in the
 * form:
 *
 * 1. **`PUT /sase/swg/policy` is an UPSERT** keyed on (scope, scope_id,
 *    category). Saving a category that already has a policy REPLACES its
 *    action; it does not add a second rule. Without the confirmation, "Save"
 *    silently changes a rule the operator may not have been looking at.
 * 2. **A tenant-scoped policy has no subject.** `scope_id` is null by
 *    definition and means "everyone" — the opposite of "not reported", which
 *    is what a dash would say.
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { createAppQueryClient } from "../../../../lib/queryClient";
import MutationErrorBanner from "../../../../components/kit/MutationErrorBanner";
import { useMutationErrorStore } from "../../../../stores/mutationErrorStore";

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
  listSwgPolicies: jest.fn(),
  setSwgPolicy: jest.fn(),
};
jest.mock("../../../../api/resources/tobogganing", () => ({ tobogganingApi }));

import SwgPolicyPage from "../SwgPolicyPage";

/**
 * Wraps the page with the SAME `QueryClient` factory `main.tsx` uses — the
 * one carrying the global `MutationCache.onError` — plus the banner it feeds,
 * so a rejected-mutation test below exercises the real shared path rather
 * than a bespoke test double of it.
 */
function renderPage(element: ReactElement) {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MutationErrorBanner />
      {element}
    </QueryClientProvider>,
  );
}

const POLICY = {
  id: "policy-1",
  scope: "tenant",
  scope_id: null,
  category: "gambling",
  action: "block",
};

beforeEach(() => {
  jest.clearAllMocks();
  useMutationErrorStore.setState({ errors: [] });
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "tobogganing" }],
    isLoading: false,
  });
  tobogganingApi.listSwgPolicies.mockResolvedValue([POLICY]);
  tobogganingApi.setSwgPolicy.mockResolvedValue({});
});

/** Open the form and fill the category + action. */
async function openForm(category: string, action: string) {
  fireEvent.click(await screen.findByTestId("tobogganing-swg-set"));
  fireEvent.change(await screen.findByLabelText(/^Category\*$/), {
    target: { value: category },
  });
  fireEvent.change(screen.getByLabelText(/^Action\*$/), {
    target: { value: action },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
}

describe("gating", () => {
  it("does not fetch when the flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<SwgPolicyPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
    expect(tobogganingApi.listSwgPolicies).not.toHaveBeenCalled();
  });

  it("does not fetch with no Tobogganing connection", () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<SwgPolicyPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listSwgPolicies).not.toHaveBeenCalled();
  });
});

describe("the policy list", () => {
  it("renders the rows the product returned", async () => {
    renderPage(<SwgPolicyPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("gambling")).toBeInTheDocument();
    expect(table.getByText("block")).toBeInTheDocument();
  });

  it('shows a tenant policy as applying to "Everyone", not a dash', async () => {
    // scope_id is null BY DEFINITION for a tenant policy. A dash says "the
    // product did not report one" — the opposite reading, and the more
    // consequential one to get wrong on a page about who is blocked.
    renderPage(<SwgPolicyPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("Everyone")).toBeInTheDocument();
    expect(table.queryByText("—")).toBeNull();
  });

  it("shows a dash when a scoped policy is missing its subject", async () => {
    // A group policy with no scope_id genuinely IS a missing value.
    tobogganingApi.listSwgPolicies.mockResolvedValue([
      { ...POLICY, scope: "group", scope_id: null },
    ]);

    renderPage(<SwgPolicyPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("—")).toBeInTheDocument();
    expect(table.queryByText("Everyone")).toBeNull();
  });

  it("surfaces a decode failure instead of reporting no policies", async () => {
    // An empty policy table reads as "nothing is blocked", which on this
    // screen is the most dangerous possible false statement.
    tobogganingApi.listSwgPolicies.mockRejectedValue(
      new Error('no "policies" key (got ["items"]) — refusing to report empty'),
    );

    renderPage(<SwgPolicyPage />);

    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText(/refusing to report empty/)).toBeInTheDocument();
  });
});

describe("setting a policy", () => {
  it("saves a new category without confirming", async () => {
    // Nothing is being replaced, so a confirmation would be noise the
    // operator learns to click through.
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("malware", "drop");

    await waitFor(() =>
      expect(tobogganingApi.setSwgPolicy).toHaveBeenCalledWith(7, {
        scope: "tenant",
        scope_id: null,
        category: "malware",
        action: "drop",
      }),
    );
    expect(screen.queryByTestId("tobogganing-swg-replace-confirm")).toBeNull();
  });

  it("confirms before replacing an existing category's action", async () => {
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("gambling", "allow");

    const confirm = await screen.findByTestId(
      "tobogganing-swg-replace-confirm",
    );
    expect(confirm).toHaveTextContent(/already set to "block"/);
    expect(confirm).toHaveTextContent(/does not add a second rule/);
    expect(tobogganingApi.setSwgPolicy).not.toHaveBeenCalled();
  });

  it("replaces only once the confirmation is accepted", async () => {
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("gambling", "allow");
    fireEvent.click(
      await screen.findByTestId("tobogganing-swg-replace-confirm-confirm"),
    );

    await waitFor(() =>
      expect(tobogganingApi.setSwgPolicy).toHaveBeenCalledWith(7, {
        scope: "tenant",
        scope_id: null,
        category: "gambling",
        action: "allow",
      }),
    );
  });

  it("writes nothing when the replacement is dismissed", async () => {
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("gambling", "allow");
    fireEvent.click(
      await screen.findByTestId("tobogganing-swg-replace-confirm-cancel"),
    );

    expect(tobogganingApi.setSwgPolicy).not.toHaveBeenCalled();
  });

  it("does not confirm when the action is unchanged", async () => {
    // Re-saving the same action replaces the row with an identical one. There
    // is nothing for the operator to weigh, so there is nothing to ask.
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("gambling", "block");

    await waitFor(() => expect(tobogganingApi.setSwgPolicy).toHaveBeenCalled());
    expect(screen.queryByTestId("tobogganing-swg-replace-confirm")).toBeNull();
  });

  it("never sends a tenant field", async () => {
    // The product derives the tenant from the JWT and rejects a body tenant
    // that disagrees, so sending one could only ever produce a 403.
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("malware", "block");

    await waitFor(() => expect(tobogganingApi.setSwgPolicy).toHaveBeenCalled());
    const payload = tobogganingApi.setSwgPolicy.mock.calls[0][1];
    expect(payload).not.toHaveProperty("tenant");
  });

  it("surfaces a rejected save instead of closing silently", async () => {
    // The historical bug: submit() closed the form before awaiting the
    // mutation, so a rejected save left nothing on screen at all — see
    // SwgPolicyPage.tsx. Revert that ordering and this test goes red.
    tobogganingApi.setSwgPolicy.mockRejectedValue(
      new Error("No Tobogganing connection for the active tenant"),
    );
    renderPage(<SwgPolicyPage />);
    await screen.findByRole("table");
    await openForm("malware", "drop");

    await waitFor(() => expect(tobogganingApi.setSwgPolicy).toHaveBeenCalled());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "No Tobogganing connection for the active tenant",
    );
    // FormModalBuilder only calls its own onClose after onSubmit resolves —
    // still open here means submit() did not force it shut first.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

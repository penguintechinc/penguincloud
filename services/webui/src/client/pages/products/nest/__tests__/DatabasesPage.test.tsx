/**
 * Nest Databases screen: gating, destructive verbs, operation polling.
 *
 * The gates are the point of the first block. A Nest screen must render nothing
 * product-shaped when the feature flag is off OR the tenant has no Nest
 * connection — and, separately, must not FETCH in either case. Those are two
 * different assertions because they fail independently: hooks run before a
 * component decides what to render, so a screen showing a "disabled"
 * placeholder can already have pulled the tenant's estate into the cache. The
 * Gough phase shipped exactly that.
 *
 * The rest covers what Nest makes different from Gough: every write is
 * asynchronous, so the screen has to carry an operation handle forward from
 * each mutation and stop polling on `is_terminal`.
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

const nestApi = {
  listDatabases: jest.fn(),
  listSnapshots: jest.fn(),
  costReport: jest.fn(),
  costSummary: jest.fn(),
};
jest.mock("../../../../api/resources/nest", () => ({ nestApi }));

const nestResourcesApi = {
  createDatabase: jest.fn(),
  deleteDatabase: jest.fn(),
  performAction: jest.fn(),
  getOperation: jest.fn(),
};
jest.mock("../../../../api/resources/nestResources", () => ({
  nestResourcesApi,
  NEST_KIND_DATABASE: "database",
  NEST_OPERATION_KIND: "operation",
}));

import DatabasesPage from "../DatabasesPage";

// Same factory `main.tsx` uses — carries the global `MutationCache.onError`
// — plus the banner it feeds, so a rejected-mutation test exercises the real
// shared path rather than a bespoke test double of it.
function renderPage(element: ReactElement) {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MutationErrorBanner />
      {element}
    </QueryClientProvider>,
  );
}

const CONNECTED = {
  data: [{ id: 7, product_type: "nest" }],
  isLoading: false,
};

const DATABASE = {
  id: "uuid-1",
  name: "orders-primary",
  phase: "Ready",
  healthState: "healthy",
  resourceType: "postgres",
  storageClass: "fast-ssd",
  sizeGi: 20,
};

beforeEach(() => {
  jest.clearAllMocks();
  useMutationErrorStore.setState({ errors: [] });
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue(CONNECTED);
  nestApi.listDatabases.mockResolvedValue([DATABASE]);
  nestApi.listSnapshots.mockResolvedValue([]);
});

describe("gating", () => {
  it("renders nothing product-shaped when the flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<DatabasesPage />);

    expect(screen.getByTestId("nest-disabled")).toBeInTheDocument();
    expect(screen.queryByTestId("nest-screen")).not.toBeInTheDocument();
  });

  it("does not fetch when the flag is off", async () => {
    // The flag is a navigation gate, not a data gate — but a screen that
    // fetched anyway would still pull the tenant's estate into the cache and
    // spend the product credential doing it.
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<DatabasesPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(nestApi.listDatabases).not.toHaveBeenCalled();
    expect(nestApi.listSnapshots).not.toHaveBeenCalled();
  });

  it("renders an empty state and does not fetch with no Nest connection", async () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<DatabasesPage />);

    expect(screen.getByTestId("nest-no-connection")).toBeInTheDocument();
    expect(nestApi.listDatabases).not.toHaveBeenCalled();
  });

  it("shows a placeholder while the connection list is loading", () => {
    mockConnections.mockReturnValue({ data: undefined, isLoading: true });

    renderPage(<DatabasesPage />);

    expect(screen.getByTestId("nest-loading")).toBeInTheDocument();
  });

  it("ignores a connection to a different product", async () => {
    mockConnections.mockReturnValue({
      data: [{ id: 9, product_type: "gough" }],
      isLoading: false,
    });

    renderPage(<DatabasesPage />);

    expect(screen.getByTestId("nest-no-connection")).toBeInTheDocument();
    expect(nestApi.listDatabases).not.toHaveBeenCalled();
  });
});

describe("listing and detail", () => {
  it("keys rows by name, not by the UUID Nest also returns", async () => {
    // Every Nest route addresses a resource by name; feeding the UUID back
    // would build a detail link that 404s.
    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("nest-database-open-uuid-1")).toBeNull();
  });

  it("shows phase and health as separate facts", async () => {
    // A resource can be Ready and unhealthy; one column cannot say both.
    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));

    const facts = within(screen.getByTestId("nest-facts"));
    expect(facts.getByText("Ready")).toBeInTheDocument();
    expect(facts.getByText("postgres")).toBeInTheDocument();
  });

  it("surfaces a failed database list instead of reporting no resources", async () => {
    // `DatabasesPage` wires `error`/`isLoading` from `useNestDatabases`
    // straight into `DataTable`; nothing previously proved that a failed
    // GET renders visibly rather than the estate reading as empty.
    nestApi.listDatabases.mockRejectedValue({
      isAxiosError: true,
      response: { data: { error: "Quota exceeded for this tenant" } },
    });

    renderPage(<DatabasesPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Quota exceeded for this tenant");
    expect(screen.queryByText(/No data available/i)).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("nest-database-open-orders-primary"),
    ).not.toBeInTheDocument();
  });

  it("does not render the raw body of an upstream-marked database list failure", async () => {
    nestApi.listDatabases.mockRejectedValue({
      isAxiosError: true,
      response: {
        data: { error: "internal: nest-cost-calculator:8443 refused" },
        headers: { "x-portal-upstream-response": "1" },
      },
    });

    renderPage(<DatabasesPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("nest-cost-calculator:8443");
    expect(alert).toHaveTextContent(/could not be loaded/i);
  });
});

describe("destructive verbs", () => {
  it.each(["snapshot", "restore", "migrate"])(
    "requires confirmation before %s reaches the product",
    async (action) => {
      nestResourcesApi.performAction.mockResolvedValue({
        action,
        accepted: true,
        operations: [],
      });
      renderPage(<DatabasesPage />);

      await waitFor(() =>
        expect(
          screen.getByTestId("nest-database-open-orders-primary"),
        ).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));
      fireEvent.click(screen.getByTestId(`nest-database-action-${action}`));

      expect(screen.getByTestId("nest-database-confirm")).toBeInTheDocument();
      expect(nestResourcesApi.performAction).not.toHaveBeenCalled();

      fireEvent.click(screen.getByTestId("nest-database-confirm-confirm"));

      await waitFor(() =>
        expect(nestResourcesApi.performAction).toHaveBeenCalledWith(
          7,
          "orders-primary",
          action,
          undefined,
        ),
      );
    },
  );

  it("does not act when the confirmation is dismissed", async () => {
    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));
    fireEvent.click(screen.getByTestId("nest-database-action-restore"));
    fireEvent.click(screen.getByTestId("nest-database-confirm-cancel"));

    expect(nestResourcesApi.performAction).not.toHaveBeenCalled();
  });

  it("deletes by name, and only after confirmation", async () => {
    nestResourcesApi.deleteDatabase.mockResolvedValue({});
    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));
    fireEvent.click(screen.getByTestId("nest-database-delete"));

    expect(nestResourcesApi.deleteDatabase).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("nest-database-delete-confirm-confirm"));

    await waitFor(() =>
      expect(nestResourcesApi.deleteDatabase).toHaveBeenCalledWith(
        7,
        "orders-primary",
      ),
    );
  });
});

describe("operations", () => {
  it("stays hidden until something is started", async () => {
    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    // Nest exposes no operation collection here, so an empty panel would be
    // asserting "the product is idle" — which this screen cannot know.
    expect(screen.queryByTestId("nest-operations")).not.toBeInTheDocument();
  });

  it("polls the operation an action started and shows what it produced", async () => {
    nestResourcesApi.performAction.mockResolvedValue({
      action: "snapshot",
      accepted: true,
      operations: [{ id: "op-1", kind: "operation", state: "pending" }],
    });
    nestResourcesApi.getOperation.mockResolvedValue({
      id: "op-1",
      kind: "operation",
      state: "succeeded",
      status: "Succeeded",
      is_terminal: true,
      detail: "snapshot",
      resource_id: "orders-primary",
      result: { snapshotName: "orders-primary-snap-1" },
    });

    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));
    fireEvent.click(screen.getByTestId("nest-database-action-snapshot"));
    fireEvent.click(screen.getByTestId("nest-database-confirm-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("nest-operation-op-1")).toBeInTheDocument(),
    );
    expect(nestResourcesApi.getOperation).toHaveBeenCalledWith(7, "op-1");
    // `result` is the reason the contract carries it: the artefact produced.
    expect(screen.getByText("orders-primary-snap-1")).toBeInTheDocument();
  });

  it("carries a create's poll handle forward", async () => {
    // Nest answers 202 for every create, so the row is not ready when the
    // create returns — the handle is what lets the screen say so.
    nestResourcesApi.createDatabase.mockResolvedValue({
      id: "new-db",
      kind: "database",
      name: "new-db",
      status: "pending",
      operation_id: "op-create",
    });
    nestResourcesApi.getOperation.mockResolvedValue({
      id: "op-create",
      kind: "operation",
      state: "running",
      status: "Running",
      is_terminal: false,
    });

    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("nest-database-create")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-create"));

    // Anchored: a loose /name/i also matches the Namespace field, and the
    // ambiguity fails in a way that reads as "the modal never opened".
    // FormModalBuilder renders a required label as "Name*" with no space.
    const name = await screen.findByLabelText(/^Name\*$/);
    fireEvent.change(name, { target: { value: "new-db" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-operation-op-create"),
      ).toBeInTheDocument(),
    );
    expect(nestResourcesApi.getOperation).toHaveBeenCalledWith(7, "op-create");
  });

  it("surfaces a failed operation's error rather than dropping it", async () => {
    nestResourcesApi.performAction.mockResolvedValue({
      action: "migrate",
      accepted: true,
      operations: [{ id: "op-2", kind: "operation", state: "pending" }],
    });
    nestResourcesApi.getOperation.mockResolvedValue({
      id: "op-2",
      kind: "operation",
      state: "failed",
      status: "Failed",
      is_terminal: true,
      error: "nest.migrate.source_unreachable",
    });

    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-database-open-orders-primary"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-open-orders-primary"));
    fireEvent.click(screen.getByTestId("nest-database-action-migrate"));
    fireEvent.click(screen.getByTestId("nest-database-confirm-confirm"));

    await waitFor(() =>
      expect(
        screen.getByTestId("nest-operation-error-op-2"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("nest.migrate.source_unreachable"),
    ).toBeInTheDocument();
  });
});

describe("mutation failures", () => {
  it("surfaces a rejected create instead of failing silently", async () => {
    // No Nest product hook defined onError before this fix — the global
    // MutationCache handler in lib/queryClient.ts is what closes that gap,
    // for this screen and the other two products alike.
    nestResourcesApi.createDatabase.mockRejectedValue({
      isAxiosError: true,
      response: { data: { error: "Quota exceeded for this tenant" } },
    });

    renderPage(<DatabasesPage />);

    await waitFor(() =>
      expect(screen.getByTestId("nest-database-create")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("nest-database-create"));

    const name = await screen.findByLabelText(/^Name\*$/);
    fireEvent.change(name, { target: { value: "new-db" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(nestResourcesApi.createDatabase).toHaveBeenCalled(),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Quota exceeded for this tenant");
  });
});

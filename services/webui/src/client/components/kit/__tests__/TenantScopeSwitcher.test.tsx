/**
 * TenantScopeSwitcher tests.
 * Covers dropdown behaviour, search, selection, URL sync, and the
 * click-outside listener. The roster comes from TanStack Query and the switch
 * itself from tenantStore, so both are mocked at their module boundaries.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TenantScopeSwitcher } from "../TenantScopeSwitcher";
import { useTenantStore } from "../../../stores/tenantStore";
import { useTenants } from "../../../hooks/useTenants";
import type { Tenant } from "../../../types";

const setSearchParams = jest.fn();

jest.mock("react-router", () => ({
  useSearchParams: () => [new URLSearchParams(), setSearchParams],
}));

jest.mock("../../../stores/tenantStore");
jest.mock("../../../hooks/useTenants");

const mockTenants = [
  {
    id: 1,
    name: "Provider A",
    display_name: "Provider A",
    slug: "provider-a",
    parent_tenant_id: null,
  },
  {
    id: 2,
    name: "Customer 1",
    display_name: "Customer 1",
    slug: "customer-1",
    parent_tenant_id: 1,
  },
  {
    id: 3,
    name: "Customer 2",
    display_name: "Customer 2",
    slug: "customer-2",
    parent_tenant_id: 1,
  },
] as unknown as Tenant[];

const switchTenant = jest.fn(() => Promise.resolve(true));

/** Drives the zustand selector API the component uses. */
function setStore(currentTenant: Tenant | null) {
  (useTenantStore as unknown as jest.Mock).mockImplementation(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ currentTenant, switchTenant }),
  );
}

function setTenants(tenants: Tenant[] | undefined) {
  (useTenants as jest.Mock).mockReturnValue({ data: tenants });
}

describe("TenantScopeSwitcher", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    switchTenant.mockResolvedValue(true);
    setStore(mockTenants[0]);
    setTenants(mockTenants);
  });

  it("renders trigger button with current tenant name", () => {
    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    expect(button).toHaveTextContent("Provider A");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("falls back to a placeholder when no tenant is active", () => {
    setStore(null);
    render(<TenantScopeSwitcher />);

    expect(screen.getByTestId("tenant-switcher-button")).toHaveTextContent(
      "Select Tenant",
    );
  });

  it("shows a disabled empty state when the roster is empty", () => {
    setTenants([]);
    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-empty");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("No tenants available");
  });

  it("shows the empty state while the roster query is still loading", () => {
    setTenants(undefined);
    render(<TenantScopeSwitcher />);

    expect(screen.getByTestId("tenant-switcher-empty")).toBeInTheDocument();
  });

  it("opens the dropdown when the trigger is clicked", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));

    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-option-1")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-switcher-button")).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("toggles the dropdown on repeated clicks", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);
    const button = screen.getByTestId("tenant-switcher-button");

    await user.click(button);
    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();

    await user.click(button);
    expect(
      screen.queryByTestId("tenant-switcher-search"),
    ).not.toBeInTheDocument();

    await user.click(button);
    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();
  });

  it("shows providers with their customers nested", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));

    expect(screen.getByTestId("tenant-option-1")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-option-2")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-option-3")).toBeInTheDocument();
  });

  it("filters tenants by search query", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.type(screen.getByTestId("tenant-switcher-search"), "Customer 1");

    expect(screen.getByTestId("tenant-option-2")).toBeInTheDocument();
    expect(screen.queryByTestId("tenant-option-3")).not.toBeInTheDocument();
  });

  it("reports when a search matches nothing", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.type(screen.getByTestId("tenant-switcher-search"), "nope");

    expect(screen.getByText("No tenants found")).toBeInTheDocument();
  });

  it("marks the active tenant", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));

    const current = screen.getByTestId("tenant-option-1");
    expect(current).toHaveClass("text-amber-400");
    expect(current).toHaveTextContent("✓ Current");
  });

  it("marks an active customer tenant", async () => {
    setStore(mockTenants[1]);
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));

    expect(screen.getByTestId("tenant-option-2")).toHaveTextContent(
      "✓ Current",
    );
  });

  it("delegates the switch to the store and reflects it in the URL", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.click(screen.getByTestId("tenant-option-2"));

    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(2));
    const params = setSearchParams.mock.calls[0][0] as URLSearchParams;
    expect(params.get("tenant")).toBe("2");
  });

  it("switches into a provider when its header is clicked", async () => {
    setStore(mockTenants[1]);
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.click(screen.getByTestId("tenant-option-1"));

    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(1));
  });

  it("closes the dropdown and clears the search after a switch", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.type(screen.getByTestId("tenant-switcher-search"), "Customer");
    await user.click(screen.getByTestId("tenant-option-2"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("tenant-switcher-search"),
      ).not.toBeInTheDocument(),
    );

    await user.click(screen.getByTestId("tenant-switcher-button"));
    expect(screen.getByTestId("tenant-switcher-search")).toHaveValue("");
  });

  it("keeps the dropdown open when the switch is rejected", async () => {
    switchTenant.mockResolvedValue(false);
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    await user.click(screen.getByTestId("tenant-option-2"));

    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(2));
    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();
    expect(setSearchParams).not.toHaveBeenCalled();
  });

  it("closes the dropdown on a mousedown outside it", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <TenantScopeSwitcher />
        <button data-testid="outside">outside</button>
      </div>,
    );

    await user.click(screen.getByTestId("tenant-switcher-button"));
    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId("outside"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("tenant-switcher-search"),
      ).not.toBeInTheDocument(),
    );
  });

  it("stays open on a mousedown inside it", async () => {
    const user = userEvent.setup();
    render(<TenantScopeSwitcher />);

    await user.click(screen.getByTestId("tenant-switcher-button"));
    fireEvent.mouseDown(screen.getByTestId("tenant-switcher-search"));

    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();
  });

  it("removes the click-outside listener on unmount", async () => {
    const addSpy = jest.spyOn(document, "addEventListener");
    const removeSpy = jest.spyOn(document, "removeEventListener");

    const { unmount } = render(<TenantScopeSwitcher />);
    const handler = addSpy.mock.calls.find(
      (call) => call[0] === "mousedown",
    )?.[1];

    unmount();

    expect(handler).toBeDefined();
    expect(removeSpy).toHaveBeenCalledWith("mousedown", handler);

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});

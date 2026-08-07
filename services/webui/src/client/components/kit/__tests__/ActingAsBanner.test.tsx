/**
 * ActingAsBanner tests.
 * The banner appears only when the active tenant differs from the operator's
 * home tenant, and Exit must switch the scope back.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActingAsBanner } from "../ActingAsBanner";
import { useTenantStore } from "../../../stores/tenantStore";
import { useTenants } from "../../../hooks/useTenants";
import { useAuth } from "../../../hooks/useAuth";
import type { Tenant } from "../../../types";

jest.mock("../../../stores/tenantStore");
jest.mock("../../../hooks/useTenants");
jest.mock("../../../hooks/useAuth");

const mockTenants = [
  { id: 1, name: "Provider A", display_name: "Provider A", slug: "provider-a" },
  {
    id: 2,
    name: "Customer 1",
    display_name: "Customer One",
    slug: "customer-1",
  },
  { id: 3, name: "Customer 2", display_name: "", slug: "customer-2" },
] as unknown as Tenant[];

const switchTenant = jest.fn(() => Promise.resolve(true));

function setStore(currentTenant: Tenant | null) {
  (useTenantStore as unknown as jest.Mock).mockImplementation(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ currentTenant, switchTenant }),
  );
}

function setUser(homeTenantId: number | undefined | null) {
  (useAuth as jest.Mock).mockReturnValue({
    user: homeTenantId === null ? null : { home_tenant_id: homeTenantId },
  });
}

describe("ActingAsBanner", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    switchTenant.mockResolvedValue(true);
    (useTenants as jest.Mock).mockReturnValue({ data: mockTenants });
    setStore(mockTenants[1]);
    setUser(1);
  });

  it("renders when the active tenant is not the home tenant", () => {
    render(<ActingAsBanner />);

    expect(screen.getByTestId("acting-as-banner")).toBeInTheDocument();
    expect(screen.getByText("Customer One")).toBeInTheDocument();
  });

  it("exposes a status role and a descriptive label", () => {
    render(<ActingAsBanner />);

    const banner = screen.getByTestId("acting-as-banner");
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveAttribute("aria-label", "Acting as Customer One");
  });

  it("falls back to the tenant name when there is no display name", () => {
    setStore(mockTenants[2]);
    render(<ActingAsBanner />);

    expect(screen.getByText("Customer 2")).toBeInTheDocument();
  });

  it("does not render while acting in the home tenant", () => {
    setStore(mockTenants[0]);
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("does not render when no tenant is active", () => {
    setStore(null);
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("does not render when there is no signed-in user", () => {
    setUser(null);
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("does not render when the user has no home tenant", () => {
    setUser(undefined);
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("does not render when the home tenant is not in the roster", () => {
    setUser(999);
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("does not render while the roster is still loading", () => {
    (useTenants as jest.Mock).mockReturnValue({ data: undefined });
    render(<ActingAsBanner />);

    expect(screen.queryByTestId("acting-as-banner")).not.toBeInTheDocument();
  });

  it("switches back to the home tenant on Exit", async () => {
    const user = userEvent.setup();
    render(<ActingAsBanner />);

    await user.click(screen.getByTestId("exit-acting-as-button"));

    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(1));
  });

  it("logs a sanitized message when the exit switch fails", async () => {
    switchTenant.mockResolvedValue(false);
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<ActingAsBanner />);

    await user.click(screen.getByTestId("exit-acting-as-button"));

    await waitFor(() =>
      expect(logSpy.mock.calls.flat().join(" ")).toContain(
        "[ActingAsBanner] ExitFailed",
      ),
    );
    logSpy.mockRestore();
  });

  it("labels the exit control for screen readers", () => {
    render(<ActingAsBanner />);

    expect(screen.getByTestId("exit-acting-as-button")).toHaveAttribute(
      "aria-label",
      "Exit acting as tenant",
    );
  });
});

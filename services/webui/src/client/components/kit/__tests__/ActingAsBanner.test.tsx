/**
 * ActingAsBanner component tests.
 * Covers: display when acting-as, exit button, banner visibility.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActingAsBanner } from "../ActingAsBanner";
import { useTenantStore } from "../../../stores/tenantStore";
import { useAuth } from "../../../hooks/useAuth";
import api from "../../../lib/api";

jest.mock("../../../stores/tenantStore");
jest.mock("../../../hooks/useAuth");
jest.mock("../../../lib/api");

const mockTenants = [
  {
    id: 1,
    name: "Provider A",
    display_name: "Provider A",
    slug: "provider-a",
    parent_tenant_id: null,
    kind: "provider",
    depth: 0,
  },
  {
    id: 2,
    name: "Customer 1",
    display_name: "Customer 1",
    slug: "customer-1",
    parent_tenant_id: 1,
    kind: "customer",
    depth: 1,
  },
];

describe("ActingAsBanner", () => {
  const mockSetCurrentTenant = jest.fn();
  const mockUser = {
    id: 1,
    email: "user@example.com",
    full_name: "Test User",
    role: "admin" as const,
    is_active: true,
    created_at: "2025-01-01",
    updated_at: "2025-01-01",
    home_tenant_id: 1,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[0],
      setCurrentTenant: mockSetCurrentTenant,
    });
    (useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
    });
  });

  it("does not render when acting as home tenant", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[0], // Same as home_tenant_id
      setCurrentTenant: mockSetCurrentTenant,
    });

    const { container } = render(<ActingAsBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders banner when acting as different tenant", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1], // Acting as customer, but home is provider
      setCurrentTenant: mockSetCurrentTenant,
    });

    render(<ActingAsBanner />);

    const banner = screen.getByTestId("acting-as-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent("Acting as Customer 1");
  });

  it("displays customer name in banner", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    render(<ActingAsBanner />);

    expect(screen.getByText("Customer 1")).toBeInTheDocument();
  });

  it("has proper ARIA role and label", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    render(<ActingAsBanner />);

    const banner = screen.getByTestId("acting-as-banner");
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveAttribute("aria-label", "Acting as Customer 1");
  });

  it("shows exit button", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    render(<ActingAsBanner />);

    const exitButton = screen.getByTestId("exit-acting-as-button");
    expect(exitButton).toBeInTheDocument();
    expect(exitButton).toHaveTextContent("Exit");
  });

  it("calls API to exit acting-as when exit button clicked", async () => {
    const mockResponse = {
      data: {
        access_token: "home-token",
        tenant: mockTenants[0],
      },
    };
    (api.post as jest.Mock).mockResolvedValue(mockResponse);

    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    const user = userEvent.setup();

    render(<ActingAsBanner />);

    const exitButton = screen.getByTestId("exit-acting-as-button");
    await user.click(exitButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/tenants/1/switch");
    });
  });

  it("updates store when exiting acting-as", async () => {
    const mockResponse = {
      data: {
        access_token: "home-token",
        tenant: mockTenants[0],
      },
    };
    (api.post as jest.Mock).mockResolvedValue(mockResponse);

    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    const user = userEvent.setup();

    render(<ActingAsBanner />);

    const exitButton = screen.getByTestId("exit-acting-as-button");
    await user.click(exitButton);

    await waitFor(() => {
      expect(mockSetCurrentTenant).toHaveBeenCalledWith(mockTenants[0]);
    });
  });

  it("does not render when home tenant is not found", () => {
    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });
    (useAuth as jest.Mock).mockReturnValue({
      user: { ...mockUser, home_tenant_id: 999 }, // Non-existent tenant
    });

    const { container } = render(<ActingAsBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("does not render when user is not logged in", () => {
    (useAuth as jest.Mock).mockReturnValue({
      user: null,
    });

    const { container } = render(<ActingAsBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("handles API errors gracefully", async () => {
    const mockError = new Error("API Error");
    (api.post as jest.Mock).mockRejectedValue(mockError);

    const consoleSpy = jest.spyOn(console, "error").mockImplementation();

    (useTenantStore as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[1],
      setCurrentTenant: mockSetCurrentTenant,
    });

    const user = userEvent.setup();

    render(<ActingAsBanner />);

    const exitButton = screen.getByTestId("exit-acting-as-button");
    await user.click(exitButton);

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });
});

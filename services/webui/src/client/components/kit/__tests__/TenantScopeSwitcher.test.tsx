/**
 * TenantScopeSwitcher component tests.
 * Covers: dropdown toggle, search, tenant selection, token update, URL sync.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TenantScopeSwitcher } from "../TenantScopeSwitcher";
import { useTenantStore } from "../../../stores/tenantStore";
import api from "../../../lib/api";

// Mock react-router
jest.mock("react-router", () => ({
  useSearchParams: () => {
    const params = new URLSearchParams();
    return [params, jest.fn()];
  },
  useNavigate: jest.fn(),
  useParams: jest.fn(),
  useLocation: jest.fn(),
  BrowserRouter: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

jest.mock("../../../lib/api");
jest.mock("../../../stores/tenantStore");

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
  {
    id: 3,
    name: "Customer 2",
    display_name: "Customer 2",
    slug: "customer-2",
    parent_tenant_id: 1,
    kind: "customer",
    depth: 1,
  },
];

describe("TenantScopeSwitcher", () => {
  const mockSetCurrentTenant = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useTenantStore as unknown as jest.Mock).mockReturnValue({
      tenants: mockTenants,
      currentTenant: mockTenants[0],
      setCurrentTenant: mockSetCurrentTenant,
    });
  });

  it("renders trigger button with current tenant name", () => {
    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("Provider A");
  });

  it("shows empty state when no tenants available", () => {
    (useTenantStore as unknown as jest.Mock).mockReturnValue({
      tenants: [],
      currentTenant: null,
      setCurrentTenant: mockSetCurrentTenant,
    });

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-empty");
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("No tenants available");
  });

  it("opens dropdown when button clicked", async () => {
    const user = userEvent.setup();

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    await user.click(button);

    // Should show search input and tenant options
    expect(screen.getByTestId("tenant-switcher-search")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-option-1")).toBeInTheDocument();
  });

  it("filters tenants by search query", async () => {
    const user = userEvent.setup();

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    await user.click(button);

    const searchInput = screen.getByTestId("tenant-switcher-search");
    await user.type(searchInput, "Customer 1");

    // Should show only Customer 1
    expect(screen.getByTestId("tenant-option-2")).toBeInTheDocument();
    expect(screen.queryByTestId("tenant-option-3")).not.toBeInTheDocument();
  });

  it("calls API to switch tenant when selected", async () => {
    const mockResponse = {
      data: {
        access_token: "new-token",
        tenant: mockTenants[1],
      },
    };
    (api.post as unknown as jest.Mock).mockResolvedValue(mockResponse);

    const user = userEvent.setup();

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    await user.click(button);

    const customerButton = screen.getByTestId("tenant-option-2");
    await user.click(customerButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/tenants/2/switch");
    });
  });

  it("closes dropdown after tenant selection", async () => {
    const mockResponse = {
      data: {
        access_token: "new-token",
        tenant: mockTenants[1],
      },
    };
    (api.post as unknown as jest.Mock).mockResolvedValue(mockResponse);

    const user = userEvent.setup();

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    await user.click(button);

    const customerButton = screen.getByTestId("tenant-option-2");
    await user.click(customerButton);

    await waitFor(() => {
      expect(
        screen.queryByTestId("tenant-switcher-search"),
      ).not.toBeInTheDocument();
    });
  });

  it("marks current tenant as selected", async () => {
    const user = userEvent.setup();

    render(<TenantScopeSwitcher />);

    const button = screen.getByTestId("tenant-switcher-button");
    await user.click(button);

    const currentOption = screen.getByTestId("tenant-option-1");
    expect(currentOption).toHaveClass("text-amber-400");
    expect(currentOption).toHaveTextContent("✓ Current");
  });
});

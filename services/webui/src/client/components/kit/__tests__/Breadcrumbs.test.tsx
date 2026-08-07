/**
 * Breadcrumbs component tests — route-derived breadcrumb navigation.
 */

import { render, screen } from "@testing-library/react";
import { Breadcrumbs } from "../Breadcrumbs";
import { useLocation } from "../../../test/__mocks__/react-router";

describe("Breadcrumbs", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  const renderWithPathname = (pathname: string) => {
    (useLocation as jest.Mock).mockReturnValue({ pathname });
    render(<Breadcrumbs />);
  };

  it("renders Dashboard breadcrumb at root", () => {
    renderWithPathname("/");
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByLabelText("Breadcrumb")).toBeInTheDocument();
  });

  it("builds breadcrumb trail for nested paths", () => {
    renderWithPathname("/tenants/123/users");
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
  });

  it("marks last breadcrumb as active with amber text", () => {
    renderWithPathname("/tenants/456");
    const active = screen.getByText("456");
    expect(active.tagName).toBe("SPAN");
    expect(active).toHaveClass("text-amber-400");
  });

  it("makes non-final breadcrumbs clickable links", () => {
    renderWithPathname("/tenants/789/details");
    const dashboardLink = screen.getByText("Dashboard");
    const tenantsLink = screen.getByText("Tenants");

    expect(dashboardLink.tagName).toBe("A");
    expect(dashboardLink).toHaveAttribute("href", "/");
    expect(tenantsLink.tagName).toBe("A");
    expect(tenantsLink).toHaveAttribute("href", "/tenants");
  });

  it("formats hyphenated segments to title case with spaces", () => {
    renderWithPathname("/tenant-detail/my-server-info");
    expect(screen.getByText("Tenant Detail")).toBeInTheDocument();
    expect(screen.getByText("My Server Info")).toBeInTheDocument();
  });

  it("preserves numeric segments as-is", () => {
    renderWithPathname("/tenants/123");
    expect(screen.getByText("123")).toBeInTheDocument();
  });

  it("capitalizes single-word segments", () => {
    renderWithPathname("/tenants/health/logs");
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();
    expect(screen.getByText("Logs")).toBeInTheDocument();
  });

  it("handles deep nested paths with multiple segments", () => {
    renderWithPathname("/gough/nodes/cluster-1/biomes/prod");
    expect(screen.getByText("Gough")).toBeInTheDocument();
    expect(screen.getByText("Nodes")).toBeInTheDocument();
    expect(screen.getByText("Cluster 1")).toBeInTheDocument();
    expect(screen.getByText("Biomes")).toBeInTheDocument();
    expect(screen.getByText("Prod")).toBeInTheDocument();
  });

  it("renders aria-label for accessibility", () => {
    renderWithPathname("/any/path");
    const nav = screen.getByLabelText("Breadcrumb");
    expect(nav).toBeInTheDocument();
  });

  it("handles trailing slashes in pathname", () => {
    renderWithPathname("/tenants/");
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Tenants")).toBeInTheDocument();
  });
});

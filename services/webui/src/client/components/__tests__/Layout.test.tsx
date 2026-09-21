/**
 * Portal shell tests.
 *
 * These exist because the shell had two defects that no unit test could see:
 * SidebarMenu received no `userRole` and therefore rendered zero menu items,
 * and the sidebar was wrapped in custom chrome that kept the library's own
 * mobile drawer off screen. Both are asserted here.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Layout from "../Layout";
import { useAuth } from "../../hooks/useAuth";
import { useTenantStore } from "../../stores/tenantStore";
import { useProductConnections } from "../../hooks/useProducts";
import { useTenantScopeBootstrap } from "../../hooks/useTenantScopeBootstrap";
import { useFeatures } from "../../hooks/useFeatures";
import { useConsoleManifests } from "../kit/useConsoleManifests";

jest.mock("../../hooks/useAuth");
jest.mock("../../stores/tenantStore");
jest.mock("../../hooks/useProducts");
jest.mock("../../hooks/useTenantScopeBootstrap");
jest.mock("../../hooks/useFeatures");
// Mocked at the hook boundary, same as `useProductConnections` above — Layout
// reads `useConsoleManifests` only to build the extension nav categories
// (`buildExtensionMenuCategories`, Design §4.1), not to prove the fetch
// chain itself (that is `useConsoleManifests.test.tsx`'s job).
jest.mock("../kit/useConsoleManifests");
jest.mock("../kit/TenantScopeSwitcher", () => ({
  TenantScopeSwitcher: () => <div data-testid="tenant-scope-switcher" />,
}));
jest.mock("../kit/ActingAsBanner", () => ({
  ActingAsBanner: () => null,
}));
jest.mock("../kit/Breadcrumbs", () => ({ Breadcrumbs: () => null }));

const logout = jest.fn();

/** Captures the props the shared SidebarMenu is called with. */
const sidebarProps: Record<string, unknown>[] = [];
jest.mock("@penguintechinc/react-libs", () => ({
  SidebarMenu: (props: Record<string, unknown>) => {
    sidebarProps.push(props);
    return <nav data-testid="sidebar" />;
  },
  AppConsoleVersion: () => <div data-testid="console-version" />,
}));

describe("Layout", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sidebarProps.length = 0;
    (useAuth as jest.Mock).mockReturnValue({
      user: { role: "admin", full_name: "Ada" },
      hasRole: (roles: string[]) => roles.includes("admin"),
      logout,
    });
    (useTenantStore as unknown as jest.Mock).mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({ currentTenant: { id: 1, name: "Acme" } }),
    );
    (useProductConnections as jest.Mock).mockReturnValue({ data: [] });
    (useTenantScopeBootstrap as jest.Mock).mockReturnValue(undefined);
    (useConsoleManifests as jest.Mock).mockReturnValue({ data: [] });
  });

  it("passes the user's role to SidebarMenu", () => {
    render(<Layout />);

    // Without this the library hides every item that declares `roles`, which
    // renders an entirely empty sidebar.
    expect(sidebarProps[0].userRole).toBe("admin");
  });

  it("hands SidebarMenu a populated category tree", () => {
    render(<Layout />);

    const categories = sidebarProps[0].categories as Array<{
      header: string;
      items: unknown[];
    }>;
    expect(categories.length).toBeGreaterThan(0);
    expect(categories.every((c) => c.items.length > 0)).toBe(true);
  });

  it("delegates the mobile drawer to SidebarMenu rather than custom chrome", async () => {
    const user = userEvent.setup();
    render(<Layout />);

    expect(sidebarProps[0].mobileOpen).toBe(false);

    await user.click(screen.getByRole("button", { name: "Toggle menu" }));

    expect(sidebarProps[sidebarProps.length - 1].mobileOpen).toBe(true);
  });

  it("appends a page-slot extension category after the hand-written ones (Design §4.1)", () => {
    (useConsoleManifests as jest.Mock).mockReturnValue({
      data: [
        {
          product_id: 9,
          product_type: "layout-ext-product",
          manifest: {
            manifest_version: 2,
            product_type: "layout-ext-product",
            display_name: "Layout Ext Product",
            nav: { items: [] },
            resources: [],
            operations: null,
            metrics: null,
            extensions: [
              {
                slot: "page",
                id: "panel",
                label: "Panel",
                resource: null,
                position: 0,
              },
            ],
          },
        },
      ],
    });

    render(<Layout />);

    const categories = sidebarProps[0].categories as Array<{
      header?: string;
      key?: string;
    }>;
    expect(categories[categories.length - 1]).toMatchObject({
      header: "Layout Ext Product Extensions",
      key: "ext-layout-ext-product",
    });
  });

  it("bootstraps the tenant scope", () => {
    render(<Layout />);

    expect(useTenantScopeBootstrap).toHaveBeenCalled();
  });

  it("fetches feature state, since every gate reads what it publishes", () => {
    // Layout is the only mount point for `GET /api/v1/features`. If it stops
    // calling the hook, the gate store is never populated and every product
    // silently renders as "behind a feature flag that is currently off" —
    // fail-closed, and therefore invisible in every other test.
    render(<Layout />);

    expect(useFeatures).toHaveBeenCalled();
  });

  it("logs out from the topbar control", async () => {
    const user = userEvent.setup();
    render(<Layout />);

    await user.click(screen.getByTestId("logout-button"));

    expect(logout).toHaveBeenCalled();
  });

  it("labels the menu toggle and reflects its state", async () => {
    const user = userEvent.setup();
    render(<Layout />);

    const toggle = screen.getByRole("button", { name: "Toggle menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

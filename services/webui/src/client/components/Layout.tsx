/**
 * Layout — Main portal shell with SidebarMenu, topbar (tenant switcher, breadcrumbs, user menu),
 * acting-as banner, and footer with version info.
 */

import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { SidebarMenu, AppConsoleVersion } from "@penguintechinc/react-libs";
import {
  Home,
  Activity,
  Building,
  Users,
  Zap,
  Lock,
  Settings,
  Database,
  Shield,
  Radio,
  Gauge,
  Menu,
} from "lucide-react";
import type { MenuCategory, MenuItem } from "@penguintechinc/react-libs";
import { useAuth } from "../hooks/useAuth";
import { useTenantStore } from "../stores/tenantStore";
import { useProductConnections } from "../hooks/useProducts";
import { TenantScopeSwitcher } from "./kit/TenantScopeSwitcher";
import { ActingAsBanner } from "./kit/ActingAsBanner";
import { Breadcrumbs } from "./kit/Breadcrumbs";
import { isProductEnabled } from "../lib/featureGates";

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { hasRole, logout } = useAuth();
  const { currentTenant } = useTenantStore();
  const connections = useProductConnections(currentTenant?.id).data ?? [];

  // Map product_type to product key for feature gating
  const productKeyMap: Record<string, string> = {
    gough: "gough",
    nest: "nest",
    tobogganing: "tobogganing",
    waddleai: "waddleai",
    waddlebot: "waddlebot",
    elder: "elder",
  };

  // Determine which product categories have connections
  const connectedProducts = new Set(
    connections.map((c) => productKeyMap[c.product_type] || c.product_type),
  );

  // Helper: check if user has required roles
  const checkRoles = (roles?: string[]): boolean => {
    if (!roles || roles.length === 0) return true;
    return hasRole(roles as Array<"admin" | "maintainer" | "viewer">);
  };

  // Helper: should category be shown?
  const shouldShowProduct = (productKey: string): boolean => {
    return connectedProducts.has(productKey) && isProductEnabled(productKey);
  };

  // Build menu categories
  const categories: MenuCategory[] = [];

  // Home category (always visible)
  const homeItems: MenuItem[] = [
    {
      name: "Dashboard",
      href: "/",
      icon: Home,
      roles: ["admin", "maintainer", "viewer"],
    },
    {
      name: "Health",
      href: "/health",
      icon: Activity,
      roles: ["admin", "maintainer", "viewer"],
    },
  ];
  categories.push({
    header: "Home",
    collapsible: false,
    items: homeItems.filter((item) => checkRoles(item.roles)),
    key: "home",
    defaultOpen: true,
  });

  // Gough category (gated by feature flag + connection)
  if (shouldShowProduct("gough")) {
    const goughItems: MenuItem[] = [
      { name: "Nodes", href: "/products/gough/nodes", icon: Gauge },
      { name: "Biomes", href: "/products/gough/biomes", icon: Building },
      { name: "Clusters", href: "/products/gough/clusters", icon: Zap },
      { name: "Agents", href: "/products/gough/agents", icon: Shield },
    ];
    categories.push({
      header: "Gough",
      collapsible: true,
      items: goughItems,
      key: "gough",
      defaultOpen: false,
    });
  }

  // Nest category (gated by feature flag + connection)
  if (shouldShowProduct("nest")) {
    const nestItems: MenuItem[] = [
      { name: "Databases", href: "/products/nest/databases", icon: Database },
      { name: "Servers", href: "/products/nest/servers", icon: Building },
      { name: "Workflows", href: "/products/nest/workflows", icon: Zap },
      { name: "Billing", href: "/products/nest/billing", icon: Lock },
      { name: "Cloud", href: "/products/nest/cloud", icon: Radio },
    ];
    categories.push({
      header: "Nest",
      collapsible: true,
      items: nestItems,
      key: "nest",
      defaultOpen: false,
    });
  }

  // Tobogganing category (gated by feature flag + connection)
  if (shouldShowProduct("tobogganing")) {
    const tobogganingItems: MenuItem[] = [
      { name: "SASE", href: "/products/tobogganing/sase", icon: Shield },
      { name: "SD-WAN", href: "/products/tobogganing/sdwan", icon: Radio },
      { name: "Firewall", href: "/products/tobogganing/firewall", icon: Lock },
      {
        name: "WireGuard",
        href: "/products/tobogganing/wireguard",
        icon: Zap,
      },
      {
        name: "Headend",
        href: "/products/tobogganing/headend",
        icon: Building,
      },
    ];
    categories.push({
      header: "Tobogganing",
      collapsible: true,
      items: tobogganingItems,
      key: "tobogganing",
      defaultOpen: false,
    });
  }

  // Organization category (always visible for admin/maintainer)
  const organizationItems: MenuItem[] = [
    {
      name: "Tenants",
      href: "/tenants",
      icon: Building,
      roles: ["admin", "maintainer"],
    },
    {
      name: "Users",
      href: "/users",
      icon: Users,
      roles: ["admin"],
    },
    {
      name: "Teams",
      href: "/teams",
      icon: Users,
      roles: ["admin", "maintainer"],
    },
    {
      name: "Connections",
      href: "/connections",
      icon: Zap,
      roles: ["admin", "maintainer"],
    },
    {
      name: "Audit",
      href: "/audit",
      icon: Shield,
      roles: ["admin"],
    },
    {
      name: "Settings",
      href: "/settings",
      icon: Settings,
      roles: ["admin", "maintainer"],
    },
  ];
  const filteredOrgItems = organizationItems.filter((item) =>
    checkRoles(item.roles),
  );
  if (filteredOrgItems.length > 0) {
    categories.push({
      header: "Organization",
      collapsible: true,
      items: filteredOrgItems,
      key: "organization",
      defaultOpen: false,
    });
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      {/* Sidebar (desktop) + mobile menu button */}
      <div className="lg:hidden fixed top-4 left-4 z-50">
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 rounded-lg hover:bg-slate-800 text-amber-400 lg:hidden"
          aria-label="Toggle menu"
        >
          <Menu className="w-5 h-5" />
        </button>
      </div>

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside
          className={`
            fixed lg:relative top-0 left-0 h-full w-64 bg-slate-900 border-r border-slate-700 z-40
            transition-transform duration-300 lg:translate-x-0
            ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
          `}
        >
          <SidebarMenu
            categories={categories}
            currentPath={location.pathname}
            onNavigate={(href) => {
              navigate(href);
              setMobileOpen(false);
            }}
            logo={
              <div className="text-lg font-bold text-amber-400">
                PenguinCloud
              </div>
            }
            themeMode="dark"
            colors={{
              sidebarBackground: "rgb(15, 23, 42)",
              sidebarBorder: "rgb(51, 65, 85)",
              logoSectionBorder: "rgb(51, 65, 85)",
              categoryHeaderText: "rgb(251, 191, 36)",
              menuItemText: "rgb(226, 232, 240)",
              menuItemHover: "rgb(30, 41, 59)",
              menuItemActive: "rgb(30, 41, 59)",
              menuItemActiveText: "rgb(251, 191, 36)",
            }}
            closeOnNavigate
          />
        </aside>

        {/* Mobile overlay */}
        {mobileOpen && (
          <div
            className="fixed inset-0 bg-black/50 lg:hidden z-30"
            onClick={() => setMobileOpen(false)}
          />
        )}

        {/* Main content area */}
        <main className="flex-1 flex flex-col">
          {/* Topbar */}
          <div className="border-b border-slate-700 bg-slate-900 sticky top-0 z-20">
            {/* Acting-as banner */}
            <ActingAsBanner />

            {/* Topbar content */}
            <div className="flex items-center justify-between h-16 px-6 py-3">
              <div className="flex-1">
                <Breadcrumbs />
              </div>
              <div className="flex items-center gap-4">
                <div className="w-48">
                  <TenantScopeSwitcher />
                </div>
                <button
                  onClick={logout}
                  className="text-sm text-slate-300 hover:text-amber-400 transition-colors"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>

          {/* Page content */}
          <div className="flex-1 overflow-auto p-6">
            <Outlet />
          </div>

          {/* Footer with version */}
          <div className="border-t border-slate-700 bg-slate-900 px-6 py-4">
            <AppConsoleVersion
              appName="PenguinCloud Portal"
              webuiVersion="1.0.0"
            />
          </div>
        </main>
      </div>
    </div>
  );
}

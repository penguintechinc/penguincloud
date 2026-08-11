/**
 * Portal shell: sidebar, topbar (breadcrumbs, tenant switcher, logout),
 * acting-as banner, and the version footer. The sidebar's category tree is
 * built in ./layout/menuCategories.
 */

import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { SidebarMenu, AppConsoleVersion } from "@penguintechinc/react-libs";
import { Menu } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useTenantStore } from "../stores/tenantStore";
import { useProductConnections } from "../hooks/useProducts";
import { useTenantScopeBootstrap } from "../hooks/useTenantScopeBootstrap";
import { useFeatures } from "../hooks/useFeatures";
import { TenantScopeSwitcher } from "./kit/TenantScopeSwitcher";
import { ActingAsBanner } from "./kit/ActingAsBanner";
import DevModeBanner from "./DevModeBanner";
import { Breadcrumbs } from "./kit/Breadcrumbs";
import { buildMenuCategories } from "./layout/menuCategories";

const SIDEBAR_COLORS = {
  sidebarBackground: "rgb(15, 23, 42)",
  sidebarBorder: "rgb(51, 65, 85)",
  logoSectionBorder: "rgb(51, 65, 85)",
  categoryHeaderText: "rgb(251, 191, 36)",
  menuItemText: "rgb(226, 232, 240)",
  menuItemHover: "rgb(30, 41, 59)",
  menuItemActive: "rgb(30, 41, 59)",
  menuItemActiveText: "rgb(251, 191, 36)",
};

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, hasRole, logout } = useAuth();
  const currentTenant = useTenantStore((state) => state.currentTenant);

  useTenantScopeBootstrap();
  // The single fetch of GET /api/v1/features, mounted here because Layout
  // wraps every authenticated route. Every gate elsewhere reads the store
  // this populates, so two screens rendered at the same moment cannot
  // disagree about what is enabled.
  useFeatures();
  const connections = useProductConnections(currentTenant?.id).data ?? [];

  const categories = buildMenuCategories(connections, (roles) => {
    if (!roles || roles.length === 0) return true;
    return hasRole(roles as Array<"admin" | "maintainer" | "viewer">);
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* SidebarMenu renders its own fixed desktop panel and mobile drawer;
          Layout only owns the trigger state and the content offset. Wrapping
          it in a custom translate-able <aside> left the library's desktop
          panel `hidden` below lg, so the drawer never appeared on mobile. */}
      <SidebarMenu
        categories={categories}
        currentPath={location.pathname}
        onNavigate={(href) => {
          navigate(href);
          setMobileOpen(false);
        }}
        logo={
          <div className="text-lg font-bold text-amber-400">PenguinCloud</div>
        }
        themeMode="dark"
        colors={SIDEBAR_COLORS}
        // SidebarMenu hides every item that declares `roles` when userRole is
        // undefined — omitting this renders an entirely empty sidebar.
        userRole={user?.role}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
        closeOnNavigate
      />

      <div className="lg:pl-64 flex flex-col min-h-screen min-w-0">
        <div className="border-b border-slate-700 bg-slate-900 sticky top-0 z-20">
          {/* Above ActingAsBanner and inside the sticky header: an
              unlicensed deployment must be visible without scrolling. */}
          <DevModeBanner />
          <ActingAsBanner />

          <div className="flex items-center justify-between h-16 px-4 sm:px-6 py-3 gap-3">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <button
                onClick={() => setMobileOpen(!mobileOpen)}
                className="lg:hidden p-2 rounded-lg hover:bg-slate-800 text-amber-400 focus:outline-none focus:ring-2 focus:ring-sky-500"
                aria-label="Toggle menu"
                aria-expanded={mobileOpen}
              >
                <Menu className="w-5 h-5" />
              </button>
              <div className="hidden sm:block min-w-0">
                <Breadcrumbs />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-36 sm:w-48">
                <TenantScopeSwitcher />
              </div>
              <button
                onClick={logout}
                className="text-sm text-slate-300 hover:text-amber-400 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 rounded"
                data-testid="logout-button"
                aria-label="Log out"
              >
                Logout
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 sm:p-6">
          <Outlet />
        </div>

        <div className="border-t border-slate-700 bg-slate-900 px-4 sm:px-6 py-4">
          <AppConsoleVersion
            appName="PenguinCloud Portal"
            webuiVersion="1.0.0"
          />
        </div>
      </div>
    </div>
  );
}

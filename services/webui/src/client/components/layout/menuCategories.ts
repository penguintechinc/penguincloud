/**
 * Builds the sidebar's category tree.
 *
 * Split out of Layout.tsx so the gating rules — a product category appears
 * only when a connection for it exists AND its feature gate is on — are
 * testable without rendering the whole shell.
 */

import {
  Home,
  Activity,
  Building,
  Users,
  Zap,
  Receipt,
  Settings,
  Database,
  Shield,
  Gauge,
} from "lucide-react";
import type { MenuCategory, MenuItem } from "@penguintechinc/react-libs";
import { isProductEnabled } from "../../lib/featureGates";
import type { ProductConnection, UserRole } from "../../types";

/** product_type as reported by the API → feature gate key. */
const PRODUCT_KEY_MAP: Record<string, string> = {
  gough: "gough",
  nest: "nest",
  tobogganing: "tobogganing",
  waddleai: "waddleai",
  waddlebot: "waddlebot",
  elder: "elder",
};

/**
 * Every product that declares a sidebar category, keyed by feature-gate key.
 *
 * Exported so the dead-link regression test can derive the connections it
 * builds the menu with, instead of listing them by hand. It listed three
 * products, so a fourth category added here would be invisible to the only
 * check that looks for dead links — the same shape as the original defect,
 * where the test built the menu with NO connections at all and therefore never
 * saw a single product entry.
 */
export const PRODUCT_ITEMS: Record<
  string,
  { header: string; items: MenuItem[] }
> = {
  gough: {
    header: "Gough",
    // No Clusters entry: Gough registers no cluster collection endpoint, and
    // no cluster id is reachable from any screen here. Its Node and Biome
    // models carry no cluster column, so nothing a nodes/biomes drill-down
    // could hand a detail view. A cluster is only addressable at
    // /clusters/{id}/... by an id the portal has no way to obtain, so the
    // entry would be a link to a form asking the operator to type a UUID.
    // See task-4G-report.md §Session 2.
    items: [
      { name: "Nodes", href: "/products/gough/nodes", icon: Gauge },
      { name: "Biomes", href: "/products/gough/biomes", icon: Building },
      { name: "Agents", href: "/products/gough/agents", icon: Shield },
    ],
  },
  nest: {
    header: "Nest",
    // No Servers, Cloud or Workflows entries. Those screens are not descoped
    // for effort reasons — they are unreachable. "Nest" is four services, and
    // its deployed HTTPRoute sends ALL of /api to nest-api, so `apps/manager`
    // (servers, cloud providers, scaling) and `saga-engine` (workflows) have
    // no route at the origin a Nest connection points at. The portal's
    // transport pins every call to that one origin — a credential-egress
    // control, not an inconvenience.
    //
    // The three entries existed here before the routes did, which made them
    // dead links behind an off-by-default flag. Filed upstream as
    // penguintechinc/nest#25 proposing prefix routes; they return when Nest
    // routes them. See task-4N-report.md.
    items: [
      { name: "Databases", href: "/products/nest/databases", icon: Database },
      { name: "Billing", href: "/products/nest/billing", icon: Receipt },
    ],
  },
  tobogganing: {
    header: "Tobogganing",
    // Empty until Phase 4T ships screens. It previously listed SASE, SD-WAN,
    // Firewall, WireGuard and Headend — five entries with no route behind any
    // of them, so every one was a dead link. They were invisible to the
    // dead-link test because it built the menu for a tenant with NO product
    // connections, and a product category only appears when one exists.
    //
    // Removed rather than left pending: `MENU_ITEM_ROUTES` is now asserted to
    // be a subset of `APP_ROUTES`, so an entry can only be added alongside the
    // route that serves it. 4T re-adds these with its screens.
    items: [],
  },
};

const HOME_ITEMS: MenuItem[] = [
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

const ORGANIZATION_ITEMS: MenuItem[] = [
  {
    name: "Tenants",
    href: "/tenants",
    icon: Building,
    roles: ["admin", "maintainer"],
  },
  { name: "Users", href: "/users", icon: Users, roles: ["admin"] },
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
  { name: "Audit", href: "/audit", icon: Shield, roles: ["admin"] },
  {
    name: "Settings",
    href: "/settings",
    icon: Settings,
    roles: ["admin", "maintainer"],
  },
];

export type RoleChecker = (roles?: string[]) => boolean;

/** Items with no `roles` are visible to everyone. */
function visible(items: MenuItem[], hasRoles: RoleChecker): MenuItem[] {
  return items.filter((item) => hasRoles(item.roles as UserRole[] | undefined));
}

export function buildMenuCategories(
  connections: ProductConnection[],
  hasRoles: RoleChecker,
): MenuCategory[] {
  const connected = new Set(
    connections.map((c) => PRODUCT_KEY_MAP[c.product_type] ?? c.product_type),
  );

  const categories: MenuCategory[] = [
    {
      header: "Home",
      collapsible: false,
      items: visible(HOME_ITEMS, hasRoles),
      key: "home",
      defaultOpen: true,
    },
  ];

  Object.entries(PRODUCT_ITEMS).forEach(([key, { header, items }]) => {
    // `items.length > 0` for the same reason the Organization block below
    // checks it: a category header with nothing under it reads as a screen
    // that failed to load rather than one that does not exist yet.
    if (connected.has(key) && isProductEnabled(key) && items.length > 0) {
      categories.push({
        header,
        collapsible: true,
        items,
        key,
        defaultOpen: false,
      });
    }
  });

  const orgItems = visible(ORGANIZATION_ITEMS, hasRoles);
  if (orgItems.length > 0) {
    categories.push({
      header: "Organization",
      collapsible: true,
      items: orgItems,
      key: "organization",
      defaultOpen: false,
    });
  }

  return categories;
}

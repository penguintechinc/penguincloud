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
  Lock,
  Settings,
  Database,
  Shield,
  Radio,
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

const PRODUCT_ITEMS: Record<string, { header: string; items: MenuItem[] }> = {
  gough: {
    header: "Gough",
    items: [
      { name: "Nodes", href: "/products/gough/nodes", icon: Gauge },
      { name: "Biomes", href: "/products/gough/biomes", icon: Building },
      { name: "Clusters", href: "/products/gough/clusters", icon: Zap },
      { name: "Agents", href: "/products/gough/agents", icon: Shield },
    ],
  },
  nest: {
    header: "Nest",
    items: [
      { name: "Databases", href: "/products/nest/databases", icon: Database },
      { name: "Servers", href: "/products/nest/servers", icon: Building },
      { name: "Workflows", href: "/products/nest/workflows", icon: Zap },
      { name: "Billing", href: "/products/nest/billing", icon: Lock },
      { name: "Cloud", href: "/products/nest/cloud", icon: Radio },
    ],
  },
  tobogganing: {
    header: "Tobogganing",
    items: [
      { name: "SASE", href: "/products/tobogganing/sase", icon: Shield },
      { name: "SD-WAN", href: "/products/tobogganing/sdwan", icon: Radio },
      { name: "Firewall", href: "/products/tobogganing/firewall", icon: Lock },
      { name: "WireGuard", href: "/products/tobogganing/wireguard", icon: Zap },
      {
        name: "Headend",
        href: "/products/tobogganing/headend",
        icon: Building,
      },
    ],
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
    if (connected.has(key) && isProductEnabled(key)) {
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

import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTenantStore } from '../stores/tenantStore';
import { useProductsStore } from '../stores/productsStore';
import TenantSwitcher from './TenantSwitcher';
import type { NavCategory, UserRole } from '../types';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

// Static navigation categories
const staticNavigation: NavCategory[] = [
  {
    label: 'Overview',
    items: [
      { label: 'Dashboard', path: '/', icon: '📊' },
      { label: 'Health', path: '/health', icon: '💚' },
      { label: 'Profile', path: '/profile', icon: '👤' },
    ],
  },
  {
    label: 'Management',
    roles: ['admin', 'maintainer'],
    items: [
      { label: 'Connections', path: '/connections', icon: '🔗', roles: ['admin', 'maintainer'] },
      { label: 'Tenants', path: '/tenants', icon: '🏢', roles: ['admin', 'maintainer'] },
      { label: 'Settings', path: '/settings', icon: '⚙️', roles: ['admin', 'maintainer'] },
    ],
  },
  {
    label: 'Administration',
    roles: ['admin'],
    items: [
      { label: 'Users', path: '/users', icon: '👥', roles: ['admin'] },
      { label: 'Audit Log', path: '/audit', icon: '📋', roles: ['admin'] },
    ],
  },
];

// Map product categories to sidebar display info
const categoryConfig: Record<string, { label: string; icon: string; order: number }> = {
  infrastructure: { label: 'Infrastructure', icon: '🏗️', order: 1 },
  security: { label: 'Security & Monitoring', icon: '🛡️', order: 2 },
  ai: { label: 'AI & Automation', icon: '🤖', order: 3 },
  monitoring: { label: 'Monitoring', icon: '📈', order: 4 },
  operations: { label: 'Operations', icon: '⚡', order: 5 },
  development: { label: 'Development', icon: '💻', order: 6 },
  legacy: { label: 'Legacy', icon: '📦', order: 7 },
  administration: { label: 'Admin Tools', icon: '🔧', order: 8 },
};

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation();
  const { user, logout, hasRole } = useAuth();
  const { currentTenant } = useTenantStore();
  const { connections } = useProductsStore();

  // Build dynamic product navigation from connected products
  const productNav: NavCategory[] = [];
  if (connections.length > 0) {
    const grouped: Record<string, Array<{ label: string; path: string; icon: string }>> = {};

    for (const conn of connections) {
      // Determine category from PRODUCT_CATEGORIES mapping
      const category = getCategoryForType(conn.product_type);
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push({
        label: conn.display_name,
        path: `/products/${conn.id}`,
        icon: getProductIcon(conn.product_type),
      });
    }

    // Sort by category order
    const sortedCategories = Object.entries(grouped).sort(
      ([a], [b]) => (categoryConfig[a]?.order || 99) - (categoryConfig[b]?.order || 99)
    );

    for (const [category, items] of sortedCategories) {
      const config = categoryConfig[category] || { label: category, icon: '📦', order: 99 };
      productNav.push({ label: config.label, items });
    }
  }

  // Combine static + product navigation
  const allNav = [...staticNavigation, ...productNav];

  // Filter based on user role
  const filteredNav = allNav
    .filter((category) => !category.roles || hasRole(category.roles as UserRole[]))
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => !item.roles || hasRole(item.roles as UserRole[])),
    }))
    .filter((category) => category.items.length > 0);

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : 'sidebar-expanded'}`}>
      {/* Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-dark-700">
        {!collapsed && (
          <span className="text-xl font-bold text-gold-gradient">PenguinCloud</span>
        )}
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-dark-800 text-gold-400"
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          {collapsed ? '→' : '←'}
        </button>
      </div>

      {/* Tenant Switcher */}
      {!collapsed && (
        <div className="px-4 py-3 border-b border-dark-700">
          <TenantSwitcher />
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4">
        {filteredNav.map((category) => (
          <div key={category.label} className="mb-4">
            {!collapsed && (
              <div className="sidebar-category">{category.label}</div>
            )}
            {category.items.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`sidebar-item ${isActive(item.path) ? 'sidebar-item-active' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <span className="text-lg">{item.icon}</span>
                {!collapsed && <span className="ml-3 truncate">{item.label}</span>}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      {/* User section */}
      <div className="border-t border-dark-700 p-4">
        {!collapsed && user && (
          <div className="mb-3">
            <div className="text-sm text-gold-400 truncate">{user.full_name}</div>
            <div className="text-xs text-dark-400 truncate">{user.email}</div>
            <div className="flex gap-1 mt-1">
              <span className={`badge badge-${user.role}`}>{user.role}</span>
              {currentTenant?.user_role && (
                <span className="badge badge-viewer">{currentTenant.user_role}</span>
              )}
            </div>
          </div>
        )}
        <button
          onClick={() => logout()}
          className={`w-full flex items-center ${
            collapsed ? 'justify-center' : ''
          } px-4 py-2 text-sm text-red-400 hover:bg-dark-800 rounded-lg`}
          title="Logout"
        >
          <span>🚪</span>
          {!collapsed && <span className="ml-2">Logout</span>}
        </button>
      </div>
    </aside>
  );
}

/** Map product_type to its category. */
function getCategoryForType(productType: string): string {
  const map: Record<string, string> = {
    marchproxy: 'infrastructure', squawk: 'infrastructure', articdbm: 'infrastructure',
    iceshelves: 'infrastructure', skauswatch: 'security', cerberus: 'security',
    waddleai: 'ai', waddlebot: 'ai', waddleperf: 'monitoring', icecharts: 'monitoring',
    killkrill: 'operations', tobogganing: 'operations', darwin: 'operations',
    gough: 'operations', current: 'operations', license_server: 'operations',
    nest: 'development', elder: 'legacy', admin: 'administration',
  };
  return map[productType] || 'operations';
}

/** Map product_type to an icon. */
function getProductIcon(productType: string): string {
  const icons: Record<string, string> = {
    marchproxy: '🛡️', squawk: '🌐', license_server: '🔑', skauswatch: '👁️',
    waddleai: '🧠', articdbm: '🗄️', cerberus: '🔒', waddlebot: '🤖',
    waddleperf: '📊', iceshelves: '💾', icecharts: '📈', killkrill: '🗑️',
    tobogganing: '🚀', nest: '💻', darwin: '🌿', gough: '⚙️',
    current: '⚡', elder: '📦', admin: '🔧',
  };
  return icons[productType] || '📦';
}

import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router";
import { useAuth } from "./hooks/useAuth";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import RoleGuard from "./components/RoleGuard";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Health from "./pages/Health";
import Users from "./pages/Users";
import UserDetail from "./pages/UserDetail";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import TenantList from "./pages/tenants/TenantList";
import TenantCreate from "./pages/tenants/TenantCreate";
import TenantDetail from "./pages/tenants/TenantDetail";
import ConnectionList from "./pages/connections/ConnectionList";
import ConnectionCreate from "./pages/connections/ConnectionCreate";
import ConnectionDetail from "./pages/connections/ConnectionDetail";
import AuditLog from "./pages/audit/AuditLog";
import ProductPage from "./pages/products/ProductPage";
import Teams from "./pages/Teams";
import { ProductResourceRoute } from "./components/kit";
import { ExtensionPageRoute } from "./components/extensions";
import DatabasesPage from "./pages/products/nest/DatabasesPage";
import BillingPage from "./pages/products/nest/BillingPage";
import SwgPolicyPage from "./pages/products/tobogganing/SwgPolicyPage";

function App() {
  const { isAuthenticated, isLoading, checkAuth } = useAuth();

  // The store starts in `isLoading: true` and only leaves it once auth has
  // been resolved. Without this, a visitor arriving without a token never
  // mounts a route — including /login — and sits on the spinner forever.
  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div className="text-amber-400 text-xl">Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      {/* Public routes */}
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />

      {/* Protected routes with layout */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        {/* Dashboard - all authenticated users */}
        <Route path="/" element={<Dashboard />} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />

        {/* Health - all authenticated users */}
        <Route path="/health" element={<Health />} />

        {/* Profile - all authenticated users */}
        <Route path="/profile" element={<Profile />} />

        {/* Tenants - Maintainer and Admin */}
        <Route
          path="/tenants"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <TenantList />
            </RoleGuard>
          }
        />
        <Route
          path="/tenants/new"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <TenantCreate />
            </RoleGuard>
          }
        />
        <Route
          path="/tenants/:id"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <TenantDetail />
            </RoleGuard>
          }
        />

        {/* Connections - Maintainer and Admin */}
        <Route
          path="/connections"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <ConnectionList />
            </RoleGuard>
          }
        />
        <Route
          path="/connections/new"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <ConnectionCreate />
            </RoleGuard>
          }
        />
        <Route
          path="/connections/:id"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <ConnectionDetail />
            </RoleGuard>
          }
        />

        {/* Product management - all authenticated (product-level auth via backend) */}
        <Route path="/products/:id" element={<ProductPage />} />

        {/* Extension page slots (Design §4.1/§3.4's escape hatch) — ONE
            generic, param-driven route for every product's `page`-slot
            extensions, not a route per product. `ExtensionPageRoute`
            resolves `:productType`/`:extensionId` against
            `useConsoleManifests()` and hands off to the registry
            (`components/extensions/ExtensionRegistry.ts`); an unregistered
            or undeclared slot degrades to a generic fallback, never a blank
            page. Gated the same way `ProductResourceRoute` is: the manifest
            only resolves when `penguincloud.declarative_console` is on and
            the tenant is connected to that product, so there is no separate
            flag check here. Deliberately NOT wrapped in
            `ProductResourceRoute`/`manifestCapabilities.ts` — a `page` slot
            is not a resource and does not go through the capability-subset
            gate resources do. */}
        <Route
          path="/products/:productType/ext/:extensionId"
          element={<ExtensionPageRoute />}
        />

        {/* Gough. No RoleGuard: authority is a scope question answered
            server-side; flag + connection gating live in
            `ProductResourceRoute`'s generic fallback. No Clusters route —
            see menuCategories.ts.

            Phase 8 Step 7 deleted Gough's hand-written NodesPage/
            BiomesPage/AgentsPage — `declarative_console` is default-on and
            every Gough resource is proven equivalence-exact against them
            (`ManifestResourceScreen.equivalence.test.tsx`), so they were
            replaced by the manifest console, not kept as a `fallback`. No
            `fallback` prop: `ProductResourceRoute` renders a generic
            connection-aware empty state for the (now purely hypothetical)
            case of the flag being off or the manifest going unroutable. */}
        <Route
          path="/products/gough/nodes"
          element={<ProductResourceRoute productType="gough" kind="nodes" />}
        />
        <Route
          path="/products/gough/biomes"
          element={<ProductResourceRoute productType="gough" kind="biomes" />}
        />
        <Route
          path="/products/gough/agents"
          element={<ProductResourceRoute productType="gough" kind="agents" />}
        />

        {/* Nest. No RoleGuard, for the same reason as Gough: authority is a
            scope question answered server-side, and flag + connection gating
            live in NestScreen. No Servers/Cloud/Workflows routes — those
            services are not reachable at a Nest connection's origin, see
            menuCategories.ts. Nest has no committed manifest yet
            (`adapters/nest` carries none), so `ProductResourceRoute` always
            falls back here today — wrapped anyway so Nest picks up manifest
            routing for free the moment one is committed. */}
        <Route
          path="/products/nest/databases"
          element={
            <ProductResourceRoute
              productType="nest"
              kind="databases"
              fallback={DatabasesPage}
            />
          }
        />
        <Route
          path="/products/nest/billing"
          element={
            <ProductResourceRoute
              productType="nest"
              kind="billing"
              fallback={BillingPage}
            />
          }
        />

        {/* Tobogganing. No RoleGuard, for the same reason as Gough and Nest.
            No Firewall or Headend routes: those are Tobogganing's MACHINE
            control plane, guarded by @require_machine_jwt which rejects any
            token whose `aud` is not "headend". A portal connection credential
            carries aud=="tobogganing", so no screen can ever be backed by
            them — an audience mismatch, not a scope one. See
            menuCategories.ts and task-4T-report.md.

            Phase 8 Step 7 deleted Tobogganing's hand-written ClientsPage/
            ClustersPage/PeersPage/BlockPagesPage — read-only resources,
            proven equivalence-exact against the manifest console, now
            default-on. No `fallback` prop on those four: same generic
            empty-state reasoning as Gough above.

            `swg_policy` KEEPS its hand-written `SwgPolicyPage` fallback: an
            unresolved `scope_id` ceiling means its manifest coverage is not
            yet equivalence-proven. */}
        <Route
          path="/products/tobogganing/clients"
          element={
            <ProductResourceRoute
              productType="tobogganing"
              kind="sdwan_client"
            />
          }
        />
        <Route
          path="/products/tobogganing/clusters"
          element={
            <ProductResourceRoute
              productType="tobogganing"
              kind="sdwan_cluster"
            />
          }
        />
        <Route
          path="/products/tobogganing/peers"
          element={
            <ProductResourceRoute
              productType="tobogganing"
              kind="wireguard_peer"
            />
          }
        />
        <Route
          path="/products/tobogganing/block-pages"
          element={
            <ProductResourceRoute productType="tobogganing" kind="block_page" />
          }
        />
        <Route
          path="/products/tobogganing/swg-policy"
          element={
            <ProductResourceRoute
              productType="tobogganing"
              kind="swg_policy"
              fallback={SwgPolicyPage}
            />
          }
        />

        {/* Settings - Maintainer and Admin */}
        <Route
          path="/settings"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <Settings />
            </RoleGuard>
          }
        />

        {/* User management - Admin only */}
        <Route
          path="/users"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <Users />
            </RoleGuard>
          }
        />
        <Route
          path="/users/:id"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <UserDetail />
            </RoleGuard>
          }
        />

        {/* Teams - Admin and Maintainer */}
        <Route
          path="/teams"
          element={
            <RoleGuard allowedRoles={["admin", "maintainer"]}>
              <Teams />
            </RoleGuard>
          }
        />

        {/* Audit - Admin only */}
        <Route
          path="/audit"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <AuditLog />
            </RoleGuard>
          }
        />
      </Route>

      {/* Catch all - redirect to dashboard or login */}
      <Route
        path="*"
        element={<Navigate to={isAuthenticated ? "/" : "/login"} replace />}
      />
    </Routes>
  );
}

export default App;

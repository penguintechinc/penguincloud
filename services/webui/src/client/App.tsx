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
import NodesPage from "./pages/products/gough/NodesPage";
import BiomesPage from "./pages/products/gough/BiomesPage";
import AgentsPage from "./pages/products/gough/AgentsPage";
import DatabasesPage from "./pages/products/nest/DatabasesPage";
import BillingPage from "./pages/products/nest/BillingPage";
import ClientsPage from "./pages/products/tobogganing/ClientsPage";
import ClustersPage from "./pages/products/tobogganing/ClustersPage";
import PeersPage from "./pages/products/tobogganing/PeersPage";

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

        {/* Gough. No RoleGuard: authority is a scope question answered
            server-side; flag + connection gating live in GoughScreen. No
            Clusters route — see menuCategories.ts. */}
        <Route path="/products/gough/nodes" element={<NodesPage />} />
        <Route path="/products/gough/biomes" element={<BiomesPage />} />
        <Route path="/products/gough/agents" element={<AgentsPage />} />

        {/* Nest. No RoleGuard, for the same reason as Gough: authority is a
            scope question answered server-side, and flag + connection gating
            live in NestScreen. No Servers/Cloud/Workflows routes — those
            services are not reachable at a Nest connection's origin, see
            menuCategories.ts. */}
        <Route path="/products/nest/databases" element={<DatabasesPage />} />
        <Route path="/products/nest/billing" element={<BillingPage />} />

        {/* Tobogganing. No RoleGuard, for the same reason as Gough and Nest.
            No Firewall or Headend routes: those are Tobogganing's MACHINE
            control plane, guarded by @require_machine_jwt which rejects any
            token whose `aud` is not "headend". A portal connection credential
            carries aud=="tobogganing", so no screen can ever be backed by
            them — an audience mismatch, not a scope one. See
            menuCategories.ts and task-4T-report.md. */}
        <Route path="/products/tobogganing/clients" element={<ClientsPage />} />
        <Route
          path="/products/tobogganing/clusters"
          element={<ClustersPage />}
        />
        <Route path="/products/tobogganing/peers" element={<PeersPage />} />

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

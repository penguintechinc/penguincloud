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

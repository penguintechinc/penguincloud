/**
 * Tenant list. The roster is server state (TanStack Query); only the act of
 * switching scope touches the zustand store, which holds the active tenant.
 */

import { Link, useNavigate } from "react-router";
import { useTenantStore } from "../../stores/tenantStore";
import { useTenants } from "../../hooks/useTenants";
import Card from "../../components/Card";

export default function TenantList() {
  const switchTenant = useTenantStore((state) => state.switchTenant);
  const tenantsQuery = useTenants();
  const navigate = useNavigate();

  const tenants = tenantsQuery.data ?? [];

  const handleSwitch = async (tenantId: number) => {
    await switchTenant(tenantId);
    navigate("/");
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">Tenants</h1>
          <p className="text-slate-400 mt-1">Manage your organizations</p>
        </div>
        <Link to="/tenants/new" className="btn btn-primary">
          Create Tenant
        </Link>
      </div>

      {tenantsQuery.isLoading ? (
        <div className="animate-pulse space-y-4" data-testid="tenants-loading">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-20 bg-slate-700 rounded" />
          ))}
        </div>
      ) : tenants.length === 0 ? (
        <Card title="No Tenants">
          <p className="text-slate-400 mb-4">
            You don&apos;t belong to any tenants yet.
          </p>
          <Link to="/tenants/new" className="btn btn-primary">
            Create Your First Tenant
          </Link>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="tenant-list">
          {tenants.map((tenant) => (
            <Card key={tenant.id} title="">
              <div className="flex items-center justify-between">
                <div>
                  <Link
                    to={`/tenants/${tenant.id}`}
                    className="text-lg font-medium text-amber-400 hover:underline"
                  >
                    {tenant.display_name || tenant.name}
                  </Link>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-sm text-slate-400">
                      /{tenant.slug}
                    </span>
                    <span className="badge badge-viewer">{tenant.plan}</span>
                    {tenant.user_role && (
                      <span className="badge badge-admin">
                        {tenant.user_role}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleSwitch(tenant.id)}
                  className="btn btn-secondary btn-sm focus:ring-2 focus:ring-sky-500"
                  aria-label={`Switch to ${tenant.display_name || tenant.name}`}
                >
                  Switch
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

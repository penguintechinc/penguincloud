import { useTenantStore } from "../../stores/tenantStore";
import AuditTable from "../../components/AuditTable";

export default function AuditLog() {
  const { currentTenant } = useTenantStore();

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Select a tenant to view audit logs.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">Audit Log</h1>
        <p className="text-slate-400 mt-1">
          Activity history for{" "}
          {currentTenant.display_name || currentTenant.name}
        </p>
      </div>

      <AuditTable tenantId={currentTenant.id} limit={50} />
    </div>
  );
}

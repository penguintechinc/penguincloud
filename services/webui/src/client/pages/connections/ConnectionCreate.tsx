import { useNavigate } from "react-router-dom";
import { useTenantStore } from "../../stores/tenantStore";
import ConnectionWizard from "../../components/ConnectionWizard";

export default function ConnectionCreate() {
  const navigate = useNavigate();
  const { currentTenant } = useTenantStore();

  if (!currentTenant) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Select a tenant first.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">
          Register Product Connection
        </h1>
        <p className="text-slate-400 mt-1">
          Connect a PenguinTech product to{" "}
          {currentTenant.display_name || currentTenant.name}
        </p>
      </div>

      <ConnectionWizard
        tenantId={currentTenant.id}
        onComplete={(product) => navigate(`/connections/${product.id}`)}
        onCancel={() => navigate("/connections")}
      />
    </div>
  );
}

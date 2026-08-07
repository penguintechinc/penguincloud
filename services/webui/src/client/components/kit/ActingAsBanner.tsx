/**
 * Persistent amber strip shown whenever the active tenant is not the operator's
 * home tenant. Not dismissible — the only way out is Exit, which switches the
 * scope back home.
 */

import { useTenantStore } from "../../stores/tenantStore";
import { useTenants } from "../../hooks/useTenants";
import { useAuth } from "../../hooks/useAuth";

export function ActingAsBanner() {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const switchTenant = useTenantStore((state) => state.switchTenant);
  const tenantsQuery = useTenants();
  const { user } = useAuth();

  const tenants = tenantsQuery.data ?? [];
  const homeTenant = user?.home_tenant_id
    ? tenants.find((t) => t.id === user.home_tenant_id)
    : null;
  const isActingAs =
    currentTenant && homeTenant && currentTenant.id !== homeTenant.id;

  if (!isActingAs || !currentTenant) {
    return null;
  }

  async function handleExit() {
    if (!homeTenant) return;
    const switched = await switchTenant(homeTenant.id);
    if (!switched) {
      console.log("[ActingAsBanner] ExitFailed { id:", homeTenant.id, "}");
    }
  }

  return (
    <div
      className="bg-amber-400/20 border-b border-amber-400/50 px-6 py-3 flex items-center justify-between"
      role="status"
      aria-label={`Acting as ${currentTenant.display_name || currentTenant.name}`}
      data-testid="acting-as-banner"
    >
      <span className="text-amber-400 font-medium text-sm">
        Acting as{" "}
        <span className="font-bold">
          {currentTenant.display_name || currentTenant.name}
        </span>
      </span>
      <button
        onClick={handleExit}
        className="ml-4 px-3 py-1 text-sm text-amber-400 hover:text-amber-300 font-medium hover:bg-amber-400/10 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500"
        data-testid="exit-acting-as-button"
        aria-label="Exit acting as tenant"
      >
        Exit
      </button>
    </div>
  );
}

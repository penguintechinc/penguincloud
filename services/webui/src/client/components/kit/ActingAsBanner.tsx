/**
 * ActingAsBanner — Persistent amber strip showing active tenant ≠ home tenant.
 * Shows "Acting as {customer name} — Exit" affordance. Not dismissible; only via Exit.
 */

import { useTenantStore } from "../../stores/tenantStore";
import { useAuth } from "../../hooks/useAuth";
import api from "../../lib/api";

export function ActingAsBanner() {
  const { currentTenant, tenants, setCurrentTenant } = useTenantStore();
  const { user } = useAuth();

  // Determine if currently acting as a different tenant
  const homeTenant = user?.home_tenant_id
    ? tenants.find((t) => t.id === user.home_tenant_id)
    : null;
  const isActingAs =
    currentTenant && homeTenant && currentTenant.id !== homeTenant.id;

  if (!isActingAs || !currentTenant) {
    return null;
  }

  async function handleExit() {
    try {
      if (!homeTenant) return;

      const response = await api.post(`/tenants/${homeTenant.id}/switch`);
      const { access_token, tenant } = response.data;

      const { setTokens } = await import("../../lib/api");
      const refreshToken =
        localStorage.getItem("penguincloud_refresh_token") || "";
      setTokens(access_token, refreshToken);

      setCurrentTenant(tenant);
    } catch (error) {
      console.error("[ActingAsBanner] Failed to exit tenant:", error);
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
        className="ml-4 px-3 py-1 text-sm text-amber-400 hover:text-amber-300 font-medium hover:bg-amber-400/10 rounded transition-colors"
        data-testid="exit-acting-as-button"
        aria-label="Exit acting as tenant"
      >
        Exit
      </button>
    </div>
  );
}

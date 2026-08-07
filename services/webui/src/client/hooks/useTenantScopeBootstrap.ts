/**
 * Establishes an initial tenant scope once the roster has loaded.
 *
 * The scope used to be picked as a side effect of the store's fetchTenants;
 * with the roster owned by TanStack Query that had to become explicit, or a
 * freshly logged-in operator lands on the dashboard with no active tenant.
 */

import { useEffect } from "react";
import { useTenantStore } from "../stores/tenantStore";
import { useTenants } from "./useTenants";
import { useAuth } from "./useAuth";

export function useTenantScopeBootstrap(): void {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const setCurrentTenant = useTenantStore((state) => state.setCurrentTenant);
  const switchTenant = useTenantStore((state) => state.switchTenant);
  const { user } = useAuth();
  const tenantsQuery = useTenants();

  const tenants = tenantsQuery.data;
  const homeTenantId = user?.home_tenant_id;

  useEffect(() => {
    if (currentTenant || !tenants || tenants.length === 0) return;

    const home = homeTenantId
      ? tenants.find((t) => t.id === homeTenantId)
      : undefined;

    if (home) {
      // The access token already names the home tenant, so adopting it needs
      // no round trip.
      console.log("[TenantScope] Bootstrap { source: 'home' }");
      setCurrentTenant(home);
      return;
    }

    // No home tenant in the roster: the token is not scoped to whatever we
    // pick, so this has to go through a real switch to be re-issued.
    console.log("[TenantScope] Bootstrap { source: 'switch' }");
    void switchTenant(tenants[0].id);
  }, [currentTenant, tenants, homeTenantId, setCurrentTenant, switchTenant]);
}

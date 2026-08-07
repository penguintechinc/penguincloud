import { useEffect } from "react";
import { useTenantStore } from "../stores/tenantStore";

export function useTenant() {
  const {
    tenants,
    currentTenant,
    members,
    usage,
    isLoading,
    fetchTenants,
    switchTenant,
    createTenant,
    updateTenant,
    deleteTenant,
    fetchMembers,
    addMember,
    removeMember,
    fetchUsage,
  } = useTenantStore();

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  // The connection/overview prefetch that used to live here is gone: those are
  // TanStack queries now, keyed by tenant id, so each consumer fetches what it
  // needs and a tenant switch invalidates by key rather than by imperative
  // refetch from this hook.

  return {
    tenants,
    currentTenant,
    members,
    usage,
    isLoading,
    switchTenant,
    createTenant,
    updateTenant,
    deleteTenant,
    fetchMembers,
    addMember,
    removeMember,
    fetchUsage,
    hasTenantRole: (roles: string[]) => {
      if (!currentTenant?.user_role) return false;
      return roles.includes(currentTenant.user_role);
    },
    isTenantAdmin: () => {
      const role = currentTenant?.user_role;
      return role === "owner" || role === "admin";
    },
  };
}

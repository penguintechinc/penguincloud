import { useEffect } from 'react';
import { useTenantStore } from '../stores/tenantStore';
import { useProductsStore } from '../stores/productsStore';

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

  const { fetchConnections, fetchOverview } = useProductsStore();

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  useEffect(() => {
    if (currentTenant) {
      fetchConnections(currentTenant.id);
      fetchOverview(currentTenant.id);
    }
  }, [currentTenant, fetchConnections, fetchOverview]);

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
      return role === 'owner' || role === 'admin';
    },
  };
}

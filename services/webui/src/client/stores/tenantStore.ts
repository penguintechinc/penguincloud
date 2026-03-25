import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '../lib/api';
import type { Tenant, TenantMember, TenantUsage } from '../types';

interface TenantStore {
  tenants: Tenant[];
  currentTenant: Tenant | null;
  members: TenantMember[];
  usage: TenantUsage | null;
  isLoading: boolean;

  fetchTenants: () => Promise<void>;
  switchTenant: (tenantId: number) => Promise<void>;
  createTenant: (data: { name: string; slug: string; display_name?: string; plan?: string }) => Promise<Tenant>;
  updateTenant: (tenantId: number, data: Partial<Tenant>) => Promise<void>;
  deleteTenant: (tenantId: number) => Promise<void>;
  fetchMembers: (tenantId: number) => Promise<void>;
  addMember: (tenantId: number, userId: number, role: string) => Promise<void>;
  removeMember: (tenantId: number, userId: number) => Promise<void>;
  fetchUsage: (tenantId: number) => Promise<void>;
  setCurrentTenant: (tenant: Tenant | null) => void;
}

export const useTenantStore = create<TenantStore>()(
  persist(
    (set, get) => ({
      tenants: [],
      currentTenant: null,
      members: [],
      usage: null,
      isLoading: false,

      fetchTenants: async () => {
        set({ isLoading: true });
        try {
          const response = await api.get('/tenants');
          const tenants = response.data.tenants;
          set({ tenants, isLoading: false });

          // Auto-select first tenant if none selected
          if (!get().currentTenant && tenants.length > 0) {
            await get().switchTenant(tenants[0].id);
          }
        } catch {
          set({ isLoading: false });
        }
      },

      switchTenant: async (tenantId: number) => {
        try {
          const response = await api.post(`/tenants/${tenantId}/switch`);
          const { access_token, tenant, tenant_role } = response.data;

          // Update stored token
          const { setTokens } = await import('../lib/api');
          const stored = JSON.parse(localStorage.getItem('auth-storage') || '{}');
          setTokens(access_token, stored.state?.refreshToken || '');

          set({
            currentTenant: { ...tenant, user_role: tenant_role },
          });
        } catch (error) {
          console.error('Failed to switch tenant:', error);
        }
      },

      createTenant: async (data) => {
        const response = await api.post('/tenants', data);
        const tenant = response.data;
        set((state) => ({ tenants: [...state.tenants, tenant] }));
        return tenant;
      },

      updateTenant: async (tenantId, data) => {
        const response = await api.put(`/tenants/${tenantId}`, data);
        const updated = response.data;
        set((state) => ({
          tenants: state.tenants.map((t) => (t.id === tenantId ? updated : t)),
          currentTenant: state.currentTenant?.id === tenantId ? updated : state.currentTenant,
        }));
      },

      deleteTenant: async (tenantId) => {
        await api.delete(`/tenants/${tenantId}`);
        set((state) => ({
          tenants: state.tenants.filter((t) => t.id !== tenantId),
          currentTenant: state.currentTenant?.id === tenantId ? null : state.currentTenant,
        }));
      },

      fetchMembers: async (tenantId) => {
        const response = await api.get(`/tenants/${tenantId}/members`);
        set({ members: response.data.members });
      },

      addMember: async (tenantId, userId, role) => {
        await api.post(`/tenants/${tenantId}/members`, { user_id: userId, role });
        await get().fetchMembers(tenantId);
      },

      removeMember: async (tenantId, userId) => {
        await api.delete(`/tenants/${tenantId}/members/${userId}`);
        await get().fetchMembers(tenantId);
      },

      fetchUsage: async (tenantId) => {
        const response = await api.get(`/tenants/${tenantId}/usage`);
        set({ usage: response.data });
      },

      setCurrentTenant: (tenant) => set({ currentTenant: tenant }),
    }),
    {
      name: 'tenant-storage',
      partialize: (state) => ({
        currentTenant: state.currentTenant,
      }),
    }
  )
);

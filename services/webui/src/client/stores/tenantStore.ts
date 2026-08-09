/**
 * Active tenant scope — client state only.
 *
 * The tenant roster, members and usage counters used to live here too; they are
 * server state and now belong to TanStack Query (`hooks/useTenants.ts`). What
 * remains is the one thing the server does not own: which tenant the operator
 * is currently acting in, plus the token re-issue that makes a switch real.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import api, { setTokens } from "../lib/api";
import { portalUrl } from "../api/portalPaths";
import type { Tenant } from "../types";

interface TenantStore {
  currentTenant: Tenant | null;
  isSwitching: boolean;

  /** Resolves true when the scope actually changed. */
  switchTenant: (tenantId: number) => Promise<boolean>;
  setCurrentTenant: (tenant: Tenant | null) => void;
}

export const useTenantStore = create<TenantStore>()(
  persist(
    (set) => ({
      currentTenant: null,
      isSwitching: false,

      /**
       * Switches active scope. The server re-issues an access token whose
       * claims name the new tenant, so the token must be swapped before any
       * subsequent request goes out.
       */
      switchTenant: async (tenantId: number): Promise<boolean> => {
        set({ isSwitching: true });
        try {
          const response = await api.post(portalUrl.tenantSwitch(tenantId));
          const { access_token, refresh_token, tenant, tenant_role } =
            response.data;

          const stored = JSON.parse(
            localStorage.getItem("auth-storage") || "{}",
          );
          setTokens(
            access_token,
            refresh_token || stored.state?.refreshToken || "",
          );

          console.log("[TenantStore] Switched { tenantId:", tenantId, "}");
          set({
            currentTenant: { ...tenant, user_role: tenant_role },
            isSwitching: false,
          });
          return true;
        } catch {
          console.log("[TenantStore] SwitchFailed { tenantId:", tenantId, "}");
          set({ isSwitching: false });
          return false;
        }
      },

      setCurrentTenant: (tenant) => set({ currentTenant: tenant }),
    }),
    {
      name: "tenant-storage",
      partialize: (state) => ({
        currentTenant: state.currentTenant,
      }),
    },
  ),
);

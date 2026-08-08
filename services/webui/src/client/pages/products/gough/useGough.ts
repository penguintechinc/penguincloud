/**
 * TanStack Query hooks for the Gough screens.
 *
 * Every key is tenant-scoped (see `api/keys.ts`): without the tenant id, a
 * tenant switch reuses the previous tenant's cached rows under an identical
 * key, which is a cross-tenant data leak in the UI rather than a staleness
 * bug.
 *
 * `useGoughConnection` resolves the Gough connection for the active tenant.
 * A screen with no connection renders its own empty state — it never invents
 * a product id, so the queries below stay disabled rather than firing at a
 * placeholder.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { goughApi } from "../../../api/resources/gough";
import { queryKeys } from "../../../api/keys";
import { useProductConnections } from "../../../hooks/useProducts";
import { useTenantStore } from "../../../stores/tenantStore";
import { isProductEnabled } from "../../../lib/featureGates";
import type { GoughAgent, GoughBiome, GoughNode } from "./types";

/** The active tenant id, or undefined before a tenant is selected. */
export function useActiveTenantId(): number | undefined {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  return currentTenant?.id;
}

/**
 * The active tenant's Gough connection, and whether Gough may be used at all.
 *
 * `productId` is `undefined` when the tenant has no Gough product registered —
 * the same condition the sidebar gates the category on, so a screen reached by
 * a typed URL degrades the way the navigation does rather than erroring.
 *
 * `isEnabled` folds in the feature flag, and every query below gates on it.
 * That is not redundant with the screens' own flag check: a component's hooks
 * run before it decides what to render, so a screen that returns a
 * "disabled" placeholder has ALREADY fired its queries. Without this the flag
 * would be a navigation gate that still pulled the whole fleet into the
 * cache — caught by `renders nothing product-shaped when the flag is off` in
 * GoughScreens.test.tsx, which asserts the fetch never happens.
 */
export function useGoughConnection(): {
  tenantId: number | undefined;
  productId: number | undefined;
  isLoading: boolean;
  isEnabled: boolean;
} {
  const tenantId = useActiveTenantId();
  const isEnabled = isProductEnabled("gough");
  const { data, isLoading } = useProductConnections(tenantId);
  const connection = data?.find((item) => item.product_type === "gough");
  return { tenantId, productId: connection?.id, isLoading, isEnabled };
}

/** Generic list query for one Gough resource kind. */
function useGoughList<T>(
  kind: string,
  fetcher: (productId: number) => Promise<T[]>,
) {
  const { tenantId, productId, isLoading, isEnabled } = useGoughConnection();

  const query = useQuery({
    queryKey: queryKeys.goughResource(tenantId, productId, kind),
    queryFn: async (): Promise<T[]> => {
      // Guarded by `enabled`; the check keeps queryFn total.
      if (productId === undefined) return [];
      return fetcher(productId);
    },
    enabled: isEnabled && productId !== undefined,
  });

  return { ...query, productId, tenantId, isConnectionLoading: isLoading };
}

export const useGoughNodes = () =>
  useGoughList<GoughNode>("nodes", goughApi.listNodes);

export const useGoughBiomes = () =>
  useGoughList<GoughBiome>("biomes", goughApi.listBiomes);

export const useGoughAgents = () =>
  useGoughList<GoughAgent>("agents", goughApi.listAgents);

/**
 * Runs a mutating Gough verb and refreshes the affected list.
 *
 * Operations are invalidated alongside the resource list because the
 * destructive node verbs (`deploy`, `evacuate`) start long-running work: the
 * operations panel must pick the new operation up without a manual refresh,
 * which is the whole reason it exists.
 */
export function useGoughMutation<TVars>(
  kind: string,
  run: (productId: number, vars: TVars) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  const { tenantId, productId, isEnabled } = useGoughConnection();

  return useMutation({
    mutationFn: async (vars: TVars): Promise<unknown> => {
      if (!isEnabled || productId === undefined) {
        throw new Error("No Gough connection for the active tenant");
      }
      return run(productId, vars);
    },
    onSuccess: () => {
      console.log(`[useGoughMutation] Applied { kind: "${kind}" }`);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.goughResource(tenantId, productId, kind),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.goughOperations(tenantId, productId),
      });
    },
  });
}

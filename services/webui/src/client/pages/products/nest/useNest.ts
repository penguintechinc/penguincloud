/**
 * TanStack Query hooks for the Nest screens.
 *
 * Every key is tenant-scoped (see `api/keys.ts`). `useNestConnection` resolves
 * the Nest connection for the active tenant; a screen with no connection never
 * invents a product id, so the queries below stay disabled rather than firing
 * at a placeholder.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { nestApi } from "../../../api/resources/nest";
import { queryKeys } from "../../../api/keys";
import { useProductConnections } from "../../../hooks/useProducts";
import { useTenantStore } from "../../../stores/tenantStore";
import { isProductEnabled } from "../../../lib/featureGates";
import type { NestDatabase, NestSnapshot } from "./types";

/** The active tenant id, or undefined before a tenant is selected. */
export function useActiveTenantId(): number | undefined {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  return currentTenant?.id;
}

/**
 * The active tenant's Nest connection, and whether Nest may be used at all.
 *
 * `isEnabled` folds in the feature flag, and every query below gates on it.
 * That is NOT redundant with `NestScreen`'s own flag check: a component's hooks
 * run before it decides what to render, so a screen that returns a "disabled"
 * placeholder has ALREADY fired its queries. Without this the flag would be a
 * navigation gate that still pulled the tenant's whole estate into the cache —
 * the Gough phase shipped exactly that and it is asserted against here.
 */
export function useNestConnection(): {
  tenantId: number | undefined;
  productId: number | undefined;
  isLoading: boolean;
  isEnabled: boolean;
} {
  const tenantId = useActiveTenantId();
  const isEnabled = isProductEnabled("nest");
  const { data, isLoading } = useProductConnections(tenantId);
  const connection = data?.find((item) => item.product_type === "nest");
  return { tenantId, productId: connection?.id, isLoading, isEnabled };
}

/** Generic list query for one Nest resource kind. */
function useNestList<T>(
  kind: string,
  fetcher: (productId: number) => Promise<T[]>,
) {
  const { tenantId, productId, isLoading, isEnabled } = useNestConnection();

  const query = useQuery({
    queryKey: queryKeys.nestResource(tenantId, productId, kind),
    queryFn: async (): Promise<T[]> => {
      // Guarded by `enabled`; the check keeps queryFn total.
      if (productId === undefined) return [];
      return fetcher(productId);
    },
    enabled: isEnabled && productId !== undefined,
  });

  return { ...query, productId, tenantId, isConnectionLoading: isLoading };
}

export const useNestDatabases = () =>
  useNestList<NestDatabase>("databases", nestApi.listDatabases);

export const useNestSnapshots = () =>
  useNestList<NestSnapshot>("snapshots", nestApi.listSnapshots);

/**
 * Runs a mutating Nest verb and refreshes the affected list.
 *
 * `onSuccess` invalidates the resource list because every Nest write is
 * asynchronous: the row's `phase` changes after the response, and a screen
 * that did not refetch would show the state at the moment the write was
 * accepted for as long as the operator left the page open.
 */
export function useNestMutation<TVars, TResult>(
  kind: string,
  run: (productId: number, vars: TVars) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  const { tenantId, productId, isEnabled } = useNestConnection();

  return useMutation({
    mutationFn: async (vars: TVars): Promise<TResult> => {
      if (!isEnabled || productId === undefined) {
        throw new Error("No Nest connection for the active tenant");
      }
      return run(productId, vars);
    },
    onSuccess: () => {
      console.log(`[useNestMutation] Applied { kind: "${kind}" }`);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.nestResource(tenantId, productId, kind),
      });
    },
  });
}

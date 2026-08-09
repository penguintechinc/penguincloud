/**
 * TanStack Query hooks for the Tobogganing screens.
 *
 * Every key is tenant-scoped (see `api/keys.ts`). `useTobogganingConnection`
 * resolves the Tobogganing connection for the active tenant; a screen with no
 * connection never invents a product id, so the queries below stay disabled
 * rather than firing at a placeholder.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tobogganingApi } from "../../../api/resources/tobogganing";
import { queryKeys } from "../../../api/keys";
import { useProductConnections } from "../../../hooks/useProducts";
import { useTenantStore } from "../../../stores/tenantStore";
import { isProductEnabled } from "../../../lib/featureGates";
import type {
  TobogganingBlockPage,
  TobogganingClient,
  TobogganingCluster,
  TobogganingPeer,
  TobogganingSwgPolicy,
} from "./types";

/** The active tenant id, or undefined before a tenant is selected. */
export function useActiveTenantId(): number | undefined {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  return currentTenant?.id;
}

/**
 * The active tenant's Tobogganing connection, and whether it may be used.
 *
 * `isEnabled` folds in the feature flag, and every query below gates on it.
 * That is NOT redundant with `TobogganingScreen`'s own flag check: a
 * component's hooks run before it decides what to render, so a screen that
 * returns a "disabled" placeholder has ALREADY fired its queries. Without this
 * the flag would be a navigation gate that still pulled the tenant's whole
 * network into the cache — and spent the product credential doing it. The
 * Gough phase shipped exactly that, so it is asserted against per screen.
 */
export function useTobogganingConnection(): {
  tenantId: number | undefined;
  productId: number | undefined;
  isLoading: boolean;
  isEnabled: boolean;
} {
  const tenantId = useActiveTenantId();
  const isEnabled = isProductEnabled("tobogganing");
  const { data, isLoading } = useProductConnections(tenantId);
  const connection = data?.find((item) => item.product_type === "tobogganing");
  return { tenantId, productId: connection?.id, isLoading, isEnabled };
}

/** Generic list query for one Tobogganing resource kind. */
function useTobogganingList<T>(
  kind: string,
  fetcher: (productId: number) => Promise<T[]>,
) {
  const { tenantId, productId, isLoading, isEnabled } =
    useTobogganingConnection();

  const query = useQuery({
    queryKey: queryKeys.tobogganingResource(tenantId, productId, kind),
    queryFn: async (): Promise<T[]> => {
      // Guarded by `enabled`; the check keeps queryFn total.
      if (productId === undefined) return [];
      return fetcher(productId);
    },
    enabled: isEnabled && productId !== undefined,
  });

  return { ...query, productId, tenantId, isConnectionLoading: isLoading };
}

/** Kind names used in the query keys. One per screen. */
export const TOBOGGANING_KINDS = {
  clients: "clients",
  clusters: "clusters",
  peers: "peers",
  blockPages: "block-pages",
  swgPolicies: "swg-policies",
} as const;

export const useTobogganingClients = () =>
  useTobogganingList<TobogganingClient>(
    TOBOGGANING_KINDS.clients,
    tobogganingApi.listClients,
  );

export const useTobogganingClusters = () =>
  useTobogganingList<TobogganingCluster>(
    TOBOGGANING_KINDS.clusters,
    tobogganingApi.listClusters,
  );

export const useTobogganingPeers = () =>
  useTobogganingList<TobogganingPeer>(
    TOBOGGANING_KINDS.peers,
    tobogganingApi.listPeers,
  );

export const useTobogganingBlockPages = () =>
  useTobogganingList<TobogganingBlockPage>(
    TOBOGGANING_KINDS.blockPages,
    tobogganingApi.listBlockPages,
  );

export const useTobogganingSwgPolicies = () =>
  useTobogganingList<TobogganingSwgPolicy>(
    TOBOGGANING_KINDS.swgPolicies,
    tobogganingApi.listSwgPolicies,
  );

/**
 * Runs a mutating Tobogganing verb and refreshes the affected list.
 *
 * Every Tobogganing user-plane mutation is SYNCHRONOUS — 200/201 with the
 * resulting object, no operation to poll — so `onSuccess` invalidating the
 * list is the whole of the refresh story here, unlike Nest where the row's
 * phase keeps changing after the response.
 *
 * The mutation refuses rather than no-ops when the flag is off or no
 * connection exists: a write that silently does nothing is indistinguishable
 * from one that succeeded, which is worse than an error the screen can show.
 */
export function useTobogganingMutation<TVars, TResult>(
  kind: string,
  run: (productId: number, vars: TVars) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  const { tenantId, productId, isEnabled } = useTobogganingConnection();

  return useMutation({
    mutationFn: async (vars: TVars): Promise<TResult> => {
      if (!isEnabled || productId === undefined) {
        throw new Error("No Tobogganing connection for the active tenant");
      }
      return run(productId, vars);
    },
    onSuccess: () => {
      console.log(`[useTobogganingMutation] Applied { kind: "${kind}" }`);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.tobogganingResource(tenantId, productId, kind),
      });
    },
  });
}

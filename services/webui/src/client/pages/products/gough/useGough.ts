/**
 * TanStack Query hooks for the Gough screens.
 *
 * The tenant → connection → tenant-scoped-list-query chain is the shared
 * `useProductResource`/`useProductConnection` generics from the kit; this
 * file supplies only Gough's product identity (the `"gough"` product type,
 * the `gough.ts` API bindings, and the `queryKeys.gough()` cache root) and
 * the mutation shape that is genuinely Gough-specific (the destructive fleet
 * verbs and their operation-panel invalidation).
 *
 * Every key stays tenant-scoped (see `api/keys.ts`): without the tenant id,
 * a tenant switch reuses the previous tenant's cached rows under an
 * identical key, which is a cross-tenant data leak in the UI rather than a
 * staleness bug.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { goughApi } from "../../../api/resources/gough";
import { queryKeys } from "../../../api/keys";
import {
  useActiveTenantId,
  useProductConnection,
  useProductResource,
  type ProductConnectionState,
} from "../../../components/kit";
import type { GoughAgent, GoughBiome, GoughNode } from "./types";

export { useActiveTenantId };

/**
 * The active tenant's Gough connection, and whether Gough may be used at
 * all. See `useProductConnection` in the kit for the gating rationale — the
 * `isEnabled` flag is not redundant with `GoughScreen`'s own check, because
 * a component's hooks run before it decides what to render.
 */
export function useGoughConnection(): ProductConnectionState {
  return useProductConnection("gough");
}

/** Generic list query for one Gough resource kind. */
function useGoughList<T>(
  kind: string,
  fetcher: (productId: number) => Promise<T[]>,
) {
  return useProductResource<T>({
    productType: "gough",
    kind,
    queryKeyPrefix: queryKeys.gough(),
    fetcher,
  });
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

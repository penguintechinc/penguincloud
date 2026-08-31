/**
 * Generic tenant → connection → tenant-scoped-list-query chain shared by
 * every product's resource hooks.
 *
 * Every key built here is tenant-scoped: without the tenant id, a tenant
 * switch reuses the previous tenant's cached rows under an identical key,
 * which is a cross-tenant data leak in the UI rather than a staleness bug.
 *
 * `useProductConnection` resolves the connection for the active tenant. A
 * screen with no connection renders its own empty state — it never invents
 * a product id, so `useProductResource` stays disabled rather than firing at
 * a placeholder.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useProductConnections } from "../../hooks/useProducts";
import { useTenantStore } from "../../stores/tenantStore";
import { useProductEnabled } from "../../lib/featureGates";

/** The active tenant id, or undefined before a tenant is selected. */
export function useActiveTenantId(): number | undefined {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  return currentTenant?.id;
}

export interface ProductConnectionState {
  tenantId: number | undefined;
  productId: number | undefined;
  isLoading: boolean;
  isEnabled: boolean;
}

/**
 * The active tenant's connection for `productType`, and whether that
 * product may be used at all.
 *
 * `productId` is `undefined` when the tenant has no connection registered
 * for `productType` — the same condition the sidebar gates the category on,
 * so a screen reached by a typed URL degrades the way the navigation does
 * rather than erroring.
 *
 * `isEnabled` folds in the feature flag, and `useProductResource` gates
 * every query on it. That is not redundant with a screen's own flag check:
 * a component's hooks run before it decides what to render, so a screen
 * that returns a "disabled" placeholder has ALREADY fired its queries.
 * Without this the flag would be a navigation gate that still pulled the
 * whole resource into the cache.
 */
export function useProductConnection(
  productType: string,
): ProductConnectionState {
  const tenantId = useActiveTenantId();
  const isEnabled = useProductEnabled(productType);
  const { data, isLoading } = useProductConnections(tenantId);
  const connection = data?.find((item) => item.product_type === productType);
  return { tenantId, productId: connection?.id, isLoading, isEnabled };
}

export interface UseProductResourceOptions<T> {
  /** e.g. `"gough"` — drives the feature flag and connection lookup. */
  productType: string;
  /** Resource kind within the product, e.g. `"nodes"`. Folded into the query key. */
  kind: string;
  /**
   * Root of the query key this resource is cached under, e.g.
   * `queryKeys.gough()`. Kept as the caller's own key-factory output — not
   * reconstructed here — so a resource hook built on this generic caches
   * under the exact same key its product-specific predecessor used.
   */
  queryKeyPrefix: readonly unknown[];
  /** Fetches the list for the resolved connection's productId. */
  fetcher: (productId: number) => Promise<T[]>;
}

export type UseProductResourceResult<T> = UseQueryResult<T[]> & {
  productId: number | undefined;
  tenantId: number | undefined;
  isConnectionLoading: boolean;
};

/** Generic tenant-scoped list query for one resource kind of one product. */
export function useProductResource<T>(
  options: UseProductResourceOptions<T>,
): UseProductResourceResult<T> {
  const { productType, kind, queryKeyPrefix, fetcher } = options;
  const { tenantId, productId, isLoading, isEnabled } =
    useProductConnection(productType);

  const query = useQuery({
    queryKey: [...queryKeyPrefix, tenantId, productId, kind] as const,
    queryFn: async (): Promise<T[]> => {
      /* istanbul ignore next -- defensive: `enabled` requires productId to be
         defined before queryFn ever runs; this keeps queryFn total for the
         type checker rather than asserting past it. */
      if (productId === undefined) return [];
      return fetcher(productId);
    },
    enabled: isEnabled && productId !== undefined,
  });

  return { ...query, productId, tenantId, isConnectionLoading: isLoading };
}

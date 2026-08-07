/**
 * TanStack Query hooks for product connections and the product type catalogue.
 *
 * These replace the server-data slice that used to live in productsStore
 * (zustand). Zustand keeps client-only state — auth session, tenant scope, UI
 * prefs — while anything fetched from the API is owned by TanStack Query so
 * caching, refetching, and invalidation have exactly one implementation.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { productsApi } from "./useApi";
import { queryKeys } from "../api/keys";
import type { ProductConnection, ProductType } from "../types";

/**
 * Product connections for a tenant.
 *
 * `tenantId` is intentionally `number | undefined`: no tenant is selected on
 * first paint. The query stays disabled until one exists rather than being
 * fired with a placeholder id.
 */
export function useProductConnections(tenantId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.connectionsByTenant(tenantId ?? -1),
    queryFn: async (): Promise<ProductConnection[]> => {
      // Guarded by `enabled` below; the assertion keeps queryFn total.
      if (tenantId === undefined) return [];
      const response = await productsApi.list(tenantId);
      return response.products;
    },
    enabled: tenantId !== undefined,
  });
}

/** Global catalogue of connectable product types. */
export function useProductTypes() {
  return useQuery({
    queryKey: queryKeys.productTypes(),
    queryFn: async (): Promise<ProductType[]> => {
      const response = await productsApi.types();
      return response.product_types;
    },
    // The catalogue is effectively static for a session.
    staleTime: 1000 * 60 * 30,
  });
}

/**
 * Registers a new product connection and invalidates the connection list so
 * every consumer (sidebar, health grid, connection list) refetches together.
 */
export function useRegisterProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: Record<string, unknown>): Promise<ProductConnection> =>
      productsApi.register(data),
    onSuccess: () => {
      console.log("[useRegisterProduct] Registered { invalidating: true }");
      queryClient.invalidateQueries({ queryKey: queryKeys.connections() });
    },
  });
}

/**
 * Product connection endpoints and the connectable-product-type catalogue.
 */

import api from "../../lib/api";
import type {
  ProductConnection,
  ProductType,
  ProductManagementSchema,
  DiscoveredProduct,
} from "../../types";

export const productsApi = {
  types: async (): Promise<{ product_types: ProductType[] }> => {
    const response = await api.get("/products/types");
    return response.data;
  },
  list: async (
    tenantId: number,
  ): Promise<{ products: ProductConnection[]; count: number }> => {
    const response = await api.get("/products", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  get: async (id: number): Promise<ProductConnection> => {
    const response = await api.get(`/products/${id}`);
    return response.data;
  },
  register: async (
    data: Record<string, unknown>,
  ): Promise<ProductConnection> => {
    const response = await api.post("/products", data);
    return response.data;
  },
  update: async (
    id: number,
    data: Record<string, unknown>,
  ): Promise<ProductConnection> => {
    const response = await api.put(`/products/${id}`, data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/products/${id}`);
  },
  test: async (id: number): Promise<Record<string, unknown>> => {
    const response = await api.post(`/products/${id}/test`);
    return response.data;
  },
  health: async (id: number): Promise<Record<string, unknown>> => {
    const response = await api.get(`/products/${id}/health`);
    return response.data;
  },
  schema: async (id: number): Promise<ProductManagementSchema> => {
    const response = await api.get(`/products/${id}/schema`);
    return response.data;
  },
};

/** Network scan for products not yet registered as connections. */
export const discoveryApi = {
  scan: async (
    tenantId: number,
    ranges?: string[],
  ): Promise<{ discovered: DiscoveredProduct[]; count: number }> => {
    const response = await api.post("/discovery/scan", {
      tenant_id: tenantId,
      ranges,
    });
    return response.data;
  },
  results: async (
    tenantId: number,
  ): Promise<{ discovered: DiscoveredProduct[]; count: number }> => {
    const response = await api.get("/discovery/results", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  accept: async (
    discoveryId: number,
    tenantId: number,
    data?: Record<string, unknown>,
  ): Promise<ProductConnection> => {
    const response = await api.post(`/discovery/accept/${discoveryId}`, {
      tenant_id: tenantId,
      ...data,
    });
    return response.data;
  },
};

/** Forwards an arbitrary request to a connected product's own API. */
export const proxyApi = {
  request: async (
    productId: number,
    method: string,
    path: string,
    data?: unknown,
  ): Promise<unknown> => {
    const response = await api.request({
      method,
      url: `/proxy/${productId}/${path}`,
      data,
    });
    return response.data;
  },
};

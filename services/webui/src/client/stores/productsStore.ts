import { create } from "zustand";
import api from "../lib/api";
import type {
  ProductConnection,
  ProductType,
  DashboardOverview,
  ProductManagementSchema,
} from "../types";

interface ProductsStore {
  connections: ProductConnection[];
  productTypes: ProductType[];
  overview: DashboardOverview | null;
  isLoading: boolean;

  fetchProductTypes: () => Promise<void>;
  fetchConnections: (tenantId: number) => Promise<void>;
  fetchOverview: (tenantId: number) => Promise<void>;
  registerProduct: (
    data: Record<string, unknown>,
  ) => Promise<ProductConnection>;
  updateProduct: (
    productId: number,
    data: Record<string, unknown>,
  ) => Promise<void>;
  deleteProduct: (productId: number) => Promise<void>;
  testConnection: (productId: number) => Promise<Record<string, unknown>>;
  getProductHealth: (productId: number) => Promise<Record<string, unknown>>;
  getProductSchema: (productId: number) => Promise<ProductManagementSchema>;
}

export const useProductsStore = create<ProductsStore>()((set, get) => ({
  connections: [],
  productTypes: [],
  overview: null,
  isLoading: false,

  fetchProductTypes: async () => {
    const response = await api.get("/products/types");
    set({ productTypes: response.data.product_types });
  },

  fetchConnections: async (tenantId: number) => {
    set({ isLoading: true });
    try {
      const response = await api.get("/products", {
        params: { tenant_id: tenantId },
      });
      set({ connections: response.data.products, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  fetchOverview: async (tenantId: number) => {
    const response = await api.get("/dashboard/overview", {
      params: { tenant_id: tenantId },
    });
    set({ overview: response.data });
  },

  registerProduct: async (data) => {
    const response = await api.post("/products", data);
    const product = response.data;
    set((state) => ({ connections: [...state.connections, product] }));
    return product;
  },

  updateProduct: async (productId, data) => {
    const response = await api.put(`/products/${productId}`, data);
    const updated = response.data;
    set((state) => ({
      connections: state.connections.map((c) =>
        c.id === productId ? updated : c,
      ),
    }));
  },

  deleteProduct: async (productId) => {
    await api.delete(`/products/${productId}`);
    set((state) => ({
      connections: state.connections.filter((c) => c.id !== productId),
    }));
  },

  testConnection: async (productId) => {
    const response = await api.post(`/products/${productId}/test`);
    return response.data;
  },

  getProductHealth: async (productId) => {
    const response = await api.get(`/products/${productId}/health`);
    return response.data;
  },

  getProductSchema: async (productId) => {
    const response = await api.get(`/products/${productId}/schema`);
    return response.data;
  },
}));

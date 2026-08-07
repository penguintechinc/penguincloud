import { useState, useCallback } from "react";
import api from "../lib/api";
import type {
  User,
  CreateUserData,
  UpdateUserData,
  PaginatedResponse,
  Tenant,
  TenantMember,
  TenantUsage,
  ProductConnection,
  ProductType,
  DashboardOverview,
  AuditLog,
  DiscoveredProduct,
  ProductManagementSchema,
} from "../types";

// Generic API hook for loading states
export function useApiCall<T>() {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const execute = useCallback(async (apiCall: () => Promise<T>) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await apiCall();
      setData(result);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "An error occurred";
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { data, error, isLoading, execute, setData };
}

// Users API
export const usersApi = {
  list: async (page = 1, perPage = 20): Promise<PaginatedResponse<User>> => {
    const response = await api.get("/users", {
      params: { page, per_page: perPage },
    });
    return response.data;
  },
  get: async (id: number): Promise<User> => {
    const response = await api.get(`/users/${id}`);
    return response.data;
  },
  create: async (data: CreateUserData): Promise<User> => {
    const response = await api.post("/users", data);
    return response.data;
  },
  update: async (id: number, data: UpdateUserData): Promise<User> => {
    const response = await api.put(`/users/${id}`, data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/users/${id}`);
  },
};

// Hello world API (example)
export const helloApi = {
  get: async (): Promise<{ message: string; timestamp: string }> => {
    const response = await api.get("/hello");
    return response.data;
  },
  getProtected: async (): Promise<{
    message: string;
    user: string;
    role: string;
  }> => {
    const response = await api.get("/hello/protected");
    return response.data;
  },
};

// Go backend API (high-performance endpoints)
export const goApi = {
  status: async (): Promise<Record<string, unknown>> => {
    const response = await api.get("/go/status");
    return response.data;
  },
  numaInfo: async (): Promise<Record<string, unknown>> => {
    const response = await api.get("/go/numa/info");
    return response.data;
  },
  memoryStats: async (): Promise<Record<string, unknown>> => {
    const response = await api.get("/go/memory/stats");
    return response.data;
  },
};

// Tenants API
export const tenantsApi = {
  list: async (): Promise<{ tenants: Tenant[]; count: number }> => {
    const response = await api.get("/tenants");
    return response.data;
  },
  get: async (id: number): Promise<Tenant> => {
    const response = await api.get(`/tenants/${id}`);
    return response.data;
  },
  create: async (data: {
    name: string;
    slug: string;
    display_name?: string;
    plan?: string;
  }): Promise<Tenant> => {
    const response = await api.post("/tenants", data);
    return response.data;
  },
  update: async (id: number, data: Partial<Tenant>): Promise<Tenant> => {
    const response = await api.put(`/tenants/${id}`, data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/tenants/${id}`);
  },
  switchTenant: async (
    id: number,
  ): Promise<{ access_token: string; tenant: Tenant; tenant_role: string }> => {
    const response = await api.post(`/tenants/${id}/switch`);
    return response.data;
  },
  getMembers: async (
    id: number,
  ): Promise<{ members: TenantMember[]; count: number }> => {
    const response = await api.get(`/tenants/${id}/members`);
    return response.data;
  },
  addMember: async (
    id: number,
    userId: number,
    role: string,
  ): Promise<TenantMember> => {
    const response = await api.post(`/tenants/${id}/members`, {
      user_id: userId,
      role,
    });
    return response.data;
  },
  updateMember: async (
    tenantId: number,
    userId: number,
    role: string,
  ): Promise<TenantMember> => {
    const response = await api.put(`/tenants/${tenantId}/members/${userId}`, {
      role,
    });
    return response.data;
  },
  removeMember: async (tenantId: number, userId: number): Promise<void> => {
    await api.delete(`/tenants/${tenantId}/members/${userId}`);
  },
  getUsage: async (id: number): Promise<TenantUsage> => {
    const response = await api.get(`/tenants/${id}/usage`);
    return response.data;
  },
};

// Products API
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

// Discovery API
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

// Dashboard API
export const dashboardApi = {
  overview: async (tenantId: number): Promise<DashboardOverview> => {
    const response = await api.get("/dashboard/overview", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  health: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get("/dashboard/health", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
  activity: async (
    tenantId: number,
    limit = 20,
  ): Promise<{ activity: AuditLog[]; count: number }> => {
    const response = await api.get("/dashboard/activity", {
      params: { tenant_id: tenantId, limit },
    });
    return response.data;
  },
  alerts: async (tenantId: number): Promise<Record<string, unknown>> => {
    const response = await api.get("/dashboard/alerts", {
      params: { tenant_id: tenantId },
    });
    return response.data;
  },
};

// Audit API
export const auditApi = {
  logs: async (
    tenantId: number,
    page = 1,
    perPage = 50,
  ): Promise<PaginatedResponse<AuditLog>> => {
    const response = await api.get("/audit/logs", {
      params: { tenant_id: tenantId, page, per_page: perPage },
    });
    return response.data;
  },
  export: async (
    tenantId: number,
    format: "json" | "csv" = "json",
    limit = 1000,
  ): Promise<Blob | Record<string, unknown>> => {
    const response = await api.get("/audit/export", {
      params: { tenant_id: tenantId, format, limit },
      responseType: format === "csv" ? "blob" : "json",
    });
    return response.data;
  },
};

// Proxy API — forwards to product APIs
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

/**
 * User endpoints.
 * Thin typed wrappers over the shared axios client; caching and refetching are
 * TanStack Query's job, not this module's.
 */

import api from "../../lib/api";
import type {
  User,
  CreateUserData,
  UpdateUserData,
  PaginatedResponse,
} from "../../types";

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

/**
 * Platform-level endpoints: the sample hello routes and the Go high-performance
 * backend, both proxied through the webui server.
 */

import api from "../../lib/api";

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

import axios from "axios";
import { useTenantStore } from "../stores/tenantStore";

const api = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

// Token storage keys
const ACCESS_TOKEN_KEY = "penguincloud_access_token";
const REFRESH_TOKEN_KEY = "penguincloud_refresh_token";

let accessToken: string | null = null;
let refreshToken: string | null = null;

// Hydrate tokens from localStorage on module load
function hydrateTokens(): void {
  if (typeof window !== "undefined") {
    accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    console.log(
      "[ApiClient] Hydrate { hasAccess:",
      !!accessToken,
      "hasRefresh:",
      !!refreshToken,
      "}",
    );
  }
}

export function setTokens(access: string, refresh: string): void {
  accessToken = access;
  refreshToken = refresh;
  if (typeof window !== "undefined") {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    console.log("[ApiClient] SetTokens { stored: true }");
  }
}

export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    console.log("[ApiClient] ClearTokens { cleared: true }");
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

// Hydrate on module load
hydrateTokens();

// Request interceptor — attach access token and tenant scope
api.interceptors.request.use(
  (config) => {
    const token = accessToken;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Add tenant scope header if available
    try {
      const { currentTenant } = useTenantStore.getState();
      if (currentTenant?.id && config.headers) {
        config.headers["X-Tenant-Scope"] = currentTenant.id;
      }
    } catch {
      // Tenant store may not be available in all contexts
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor — handle 401 and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      refreshToken
    ) {
      originalRequest._retry = true;

      try {
        const response = await axios.post("/api/v1/auth/refresh", {
          refresh_token: refreshToken,
        });

        const { access_token, refresh_token: newRefresh } = response.data;
        setTokens(access_token, newRefresh);
        console.log("[ApiClient] TokenRefresh { success: true }");

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch {
        console.log("[ApiClient] TokenRefresh { error: true }");
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  },
);

export default api;

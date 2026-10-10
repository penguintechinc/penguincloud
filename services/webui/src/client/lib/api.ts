import axios from "axios";
import { useTenantStore } from "../stores/tenantStore";
import { API_BASE_PATH } from "../api/portalPaths";

const api = axios.create({
  baseURL: API_BASE_PATH,
  headers: {
    "Content-Type": "application/json",
  },
});

// BFF route that exchanges the HttpOnly refresh cookie for a fresh access
// token. It is NOT under API_BASE_PATH (it is this app's own Express route,
// not a portal API endpoint), so it is called with the raw axios instance.
const REFRESH_URL = "/api/ui/refresh";

// Double-submit CSRF: the BFF sets a readable `csrf` cookie alongside the
// HttpOnly refresh cookie, and we echo it back in this header on the
// cookie-authenticated POSTs. A cross-site request cannot read the cookie, so
// it cannot forge the header.
const CSRF_COOKIE = "csrf";
export const CSRF_HEADER = "X-CSRF-Token";

// The access token is kept in module memory ONLY — never localStorage, never
// a cookie. It is short-lived; on a 401 (and on first load, via
// useAuth.checkAuth) the client silently re-derives one from the HttpOnly
// refresh cookie through the BFF. The refresh token is never visible to this
// code. This removes the durable, XSS-readable token that previously sat in
// localStorage.
let accessToken: string | null = null;

export function setAccessToken(access: string): void {
  accessToken = access;
  console.log("[ApiClient] SetAccessToken { stored: true }");
}

export function clearAccessToken(): void {
  accessToken = null;
  console.log("[ApiClient] ClearAccessToken { cleared: true }");
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Reads the readable `csrf` cookie for the double-submit header. Returns the
 *  empty string when absent so the header is always present (the BFF rejects a
 *  mismatch either way). */
function readCsrfToken(): string {
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : "";
}

/**
 * Exchanges the HttpOnly refresh cookie for a fresh access token via the BFF.
 * The refresh token itself never passes through this code: the browser sends
 * the cookie, the BFF calls the backend server-side and rotates the cookie.
 * Resolves to the new access token (also stored in memory) or null when the
 * BFF returned no token. Rejects when there is no valid session to refresh.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const response = await axios.post(
    REFRESH_URL,
    {},
    { headers: { [CSRF_HEADER]: readCsrfToken() } },
  );
  const access =
    typeof response.data?.access_token === "string"
      ? response.data.access_token
      : null;
  if (access) setAccessToken(access);
  return access;
}

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

// Response interceptor — handle 401 by silently refreshing via the BFF cookie
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;

      try {
        const access = await refreshAccessToken();
        console.log("[ApiClient] TokenRefresh { success: true }");

        if (access && originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access}`;
        }
        return api(originalRequest);
      } catch {
        console.log("[ApiClient] TokenRefresh { error: true }");
        clearAccessToken();
        // `assign` rather than setting `href`: identical behaviour, and it is
        // a method, so it can be observed in tests (jsdom's `location.href`
        // is non-configurable).
        window.location.assign("/login");
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  },
);

export default api;

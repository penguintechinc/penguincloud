import { create } from "zustand";
import axios from "axios";
import api, {
  setAccessToken,
  clearAccessToken,
  getAccessToken,
  refreshAccessToken,
  CSRF_HEADER,
} from "../lib/api";
import type { User, LoginCredentials, AuthState } from "../types";

interface AuthStore extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  establishSession: (access: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  checkAuth: () => Promise<boolean>;
  setUser: (user: User | null) => void;
}

/** Reads the readable `csrf` cookie so the BFF logout call can carry the
 *  double-submit header. */
function readCsrfToken(): string {
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrf="));
  return match ? decodeURIComponent(match.slice("csrf=".length)) : "";
}

// NOT wrapped in zustand `persist`: nothing here is safe to write to
// localStorage. The refresh token lives only in the BFF's HttpOnly cookie,
// and the access token is deliberately memory-only (short-lived, re-derived
// from the cookie on load via checkAuth). Persisting either is exactly the
// durable-token exposure this change removes.
export const useAuthStore = create<AuthStore>()((set) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (credentials: LoginCredentials) => {
    // Note: this path talks to the portal API directly rather than the BFF
    // login seam, so it does not establish the HttpOnly refresh cookie. The
    // app logs in through the shared login page (`establishSession`); this
    // method is retained for the store contract and keeps only the
    // short-lived access token in memory.
    try {
      const response = await api.post("/auth/login", credentials);
      const { access_token, user } = response.data;

      setAccessToken(access_token);

      set({
        user,
        accessToken: access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error) {
      clearAccessToken();
      set({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: false,
      });
      throw error;
    }
  },

  /**
   * Adopts an access token obtained outside this store — the shared-library
   * login page performs its own request to the BFF, which sets the HttpOnly
   * refresh cookie and hands back only the access token. The user record is
   * then loaded from /auth/me so the identity shape has exactly one source.
   */
  establishSession: async (access: string) => {
    setAccessToken(access);
    set({
      accessToken: access,
      isAuthenticated: true,
    });

    try {
      const response = await api.get("/auth/me");
      set({ user: response.data, isLoading: false });
      console.log("[AuthStore] SessionEstablished { hydrated: true }");
    } catch {
      // The session is valid — only the profile lookup failed. Keep the
      // user authenticated; ProtectedRoute re-runs checkAuth on mount.
      set({ isLoading: false });
      console.log("[AuthStore] SessionEstablished { hydrated: false }");
    }
  },

  logout: async () => {
    try {
      // Backend revocation (Bearer-authenticated) through the proxy.
      await api.post("/auth/logout");
    } catch {
      // Ignore logout errors
    }
    try {
      // Clear the HttpOnly refresh + csrf cookies at the BFF. Double-submit
      // CSRF header required, same as refresh.
      await axios.post(
        "/api/ui/logout",
        {},
        { headers: { [CSRF_HEADER]: readCsrfToken() } },
      );
    } catch {
      // Ignore logout errors
    }
    clearAccessToken();
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  },

  fetchUser: async () => {
    try {
      const response = await api.get("/auth/me");
      set({ user: response.data, isLoading: false });
    } catch {
      set({ user: null, isLoading: false });
    }
  },

  checkAuth: async () => {
    // On a fresh load the in-memory access token is gone, but a returning
    // visitor may still hold the HttpOnly refresh cookie. Try to silently
    // re-derive an access token from it before deciding the user is
    // unauthenticated. A visitor with no cookie gets a 401 here — that is the
    // logged-out case, not an error.
    if (!getAccessToken()) {
      try {
        await refreshAccessToken();
      } catch {
        set({ user: null, isAuthenticated: false, isLoading: false });
        return false;
      }
      if (!getAccessToken()) {
        set({ user: null, isAuthenticated: false, isLoading: false });
        return false;
      }
    }

    try {
      const response = await api.get("/auth/me");
      set({
        user: response.data,
        isAuthenticated: true,
        isLoading: false,
      });
      return true;
    } catch {
      clearAccessToken();
      set({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: false,
      });
      return false;
    }
  },

  setUser: (user: User | null) => {
    set({ user });
  },
}));

// Hook for components
export const useAuth = () => {
  const store = useAuthStore();

  return {
    user: store.user,
    isAuthenticated: store.isAuthenticated,
    isLoading: store.isLoading,
    login: store.login,
    establishSession: store.establishSession,
    logout: store.logout,
    checkAuth: store.checkAuth,
    hasRole: (roles: string[]) => {
      if (!store.user) return false;
      return roles.includes(store.user.role);
    },
    isAdmin: () => store.user?.role === "admin",
    isMaintainer: () => store.user?.role === "maintainer",
    isViewer: () => store.user?.role === "viewer",
  };
};

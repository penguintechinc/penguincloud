import { create } from "zustand";
import { persist } from "zustand/middleware";
import api, { setTokens, clearTokens, getAccessToken } from "../lib/api";
import type { User, LoginCredentials, AuthState } from "../types";

interface AuthStore extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  establishSession: (access: string, refresh: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  checkAuth: () => Promise<boolean>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,

      login: async (credentials: LoginCredentials) => {
        try {
          const response = await api.post("/auth/login", credentials);
          const { access_token, refresh_token, user } = response.data;

          setTokens(access_token, refresh_token);

          set({
            user,
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          clearTokens();
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isLoading: false,
          });
          throw error;
        }
      },

      /**
       * Adopts a token pair obtained outside this store — the shared-library
       * login page performs its own request, so it hands back tokens rather
       * than credentials. The user record is then loaded from /auth/me so the
       * identity shape has exactly one source.
       */
      establishSession: async (access: string, refresh: string) => {
        setTokens(access, refresh);
        set({
          accessToken: access,
          refreshToken: refresh,
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
          await api.post("/auth/logout");
        } catch {
          // Ignore logout errors
        } finally {
          clearTokens();
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
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
        const token = getAccessToken();
        if (!token) {
          set({ isAuthenticated: false, isLoading: false });
          return false;
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
          clearTokens();
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isLoading: false,
          });
          return false;
        }
      },

      setUser: (user: User | null) => {
        set({ user });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    },
  ),
);

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

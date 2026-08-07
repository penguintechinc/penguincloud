/**
 * API client interceptor tests.
 *
 * The interceptors are exercised through real requests against a stubbed
 * adapter rather than by reaching into axios internals, so the assertions
 * cover the chain a caller actually gets.
 */

import type { AxiosRequestConfig, AxiosResponse } from "axios";

/** Response the stub adapter returns unless a test overrides it. */
function ok(config: AxiosRequestConfig): Promise<AxiosResponse> {
  return Promise.resolve({
    data: { ok: true },
    status: 200,
    statusText: "OK",
    headers: {},
    config: config as AxiosResponse["config"],
  });
}

function unauthorized(config: AxiosRequestConfig) {
  const error = new Error("Request failed with status code 401") as Error & {
    response?: { status: number };
    config?: AxiosRequestConfig;
  };
  error.response = { status: 401 };
  error.config = config;
  return Promise.reject(error);
}

/** Headers the stub adapter actually received on a given call. */
function headersOf(adapter: jest.Mock, call = 0): Record<string, unknown> {
  const config = adapter.mock.calls[call][0] as AxiosRequestConfig;
  if (!config.headers) throw new Error("request was sent with no headers");
  return config.headers as unknown as Record<string, unknown>;
}

/**
 * Loads a fresh copy of the client. The module hydrates tokens from
 * localStorage at import time, so each scenario needs its own instance.
 */
async function loadApi() {
  jest.resetModules();
  const mod = await import("../api");
  const tenantStore = await import("../../stores/tenantStore");
  // resetModules gives api.ts a fresh axios too, so the refresh call can only
  // be observed on that same copy — not on one imported at file scope.
  const axios = (await import("axios")).default;
  return { ...mod, api: mod.default, tenantStore, axios };
}

const ACCESS_KEY = "penguincloud_access_token";
const REFRESH_KEY = "penguincloud_refresh_token";

beforeEach(() => {
  localStorage.clear();
  jest.restoreAllMocks();
});

describe("token storage", () => {
  it("hydrates tokens written before the module loaded", async () => {
    localStorage.setItem(ACCESS_KEY, "stored-access");
    localStorage.setItem(REFRESH_KEY, "stored-refresh");

    const { getAccessToken } = await loadApi();

    expect(getAccessToken()).toBe("stored-access");
  });

  it("starts with no token when storage is empty", async () => {
    const { getAccessToken } = await loadApi();

    expect(getAccessToken()).toBeNull();
  });

  it("persists a token pair", async () => {
    const { setTokens, getAccessToken } = await loadApi();

    setTokens("a", "r");

    expect(getAccessToken()).toBe("a");
    expect(localStorage.getItem(ACCESS_KEY)).toBe("a");
    expect(localStorage.getItem(REFRESH_KEY)).toBe("r");
  });

  it("clears both tokens", async () => {
    const { setTokens, clearTokens, getAccessToken } = await loadApi();
    setTokens("a", "r");

    clearTokens();

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});

describe("request interceptor", () => {
  it("attaches the bearer token", async () => {
    const { api, setTokens } = await loadApi();
    setTokens("access-1", "refresh-1");
    const adapter = jest.fn(ok);
    api.defaults.adapter = adapter;

    await api.get("/widgets");

    expect(headersOf(adapter).Authorization).toBe("Bearer access-1");
  });

  it("sends no Authorization header when unauthenticated", async () => {
    const { api } = await loadApi();
    const adapter = jest.fn(ok);
    api.defaults.adapter = adapter;

    await api.get("/widgets");

    expect(headersOf(adapter).Authorization).toBeUndefined();
  });

  it("stamps X-Tenant-Scope from the active tenant", async () => {
    const { api, tenantStore } = await loadApi();
    tenantStore.useTenantStore.setState({
      currentTenant: { id: 42 } as never,
    });
    const adapter = jest.fn(ok);
    api.defaults.adapter = adapter;

    await api.get("/widgets");

    expect(headersOf(adapter)["X-Tenant-Scope"]).toBe("42");
  });

  it("omits X-Tenant-Scope when no tenant is active", async () => {
    const { api, tenantStore } = await loadApi();
    tenantStore.useTenantStore.setState({ currentTenant: null });
    const adapter = jest.fn(ok);
    api.defaults.adapter = adapter;

    await api.get("/widgets");

    expect(headersOf(adapter)["X-Tenant-Scope"]).toBeUndefined();
  });

  it("still sends the request when the tenant store throws", async () => {
    const { api, tenantStore } = await loadApi();
    jest
      .spyOn(tenantStore.useTenantStore, "getState")
      .mockImplementation(() => {
        throw new Error("store unavailable");
      });
    const adapter = jest.fn(ok);
    api.defaults.adapter = adapter;

    await expect(api.get("/widgets")).resolves.toBeDefined();
  });

  it("propagates a request-stage error", async () => {
    const { api } = await loadApi();
    const failure = new Error("bad config");
    api.interceptors.request.use(() => {
      throw failure;
    });

    await expect(api.get("/widgets")).rejects.toThrow("bad config");
  });
});

describe("response interceptor", () => {
  it("passes a successful response straight through", async () => {
    const { api } = await loadApi();
    api.defaults.adapter = jest.fn(ok);

    const response = await api.get("/widgets");

    expect(response.data).toEqual({ ok: true });
  });

  it("refreshes on 401 and replays the original request", async () => {
    const { api, setTokens, getAccessToken, axios } = await loadApi();
    setTokens("stale-access", "refresh-1");

    const post = jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "fresh-access", refresh_token: "refresh-2" },
    } as never);

    let attempt = 0;
    const adapter = jest.fn((config: AxiosRequestConfig) => {
      attempt += 1;
      return attempt === 1 ? unauthorized(config) : ok(config);
    });
    api.defaults.adapter = adapter as never;

    const response = await api.get("/widgets");

    expect(post).toHaveBeenCalledWith("/api/v1/auth/refresh", {
      refresh_token: "refresh-1",
    });
    expect(response.data).toEqual({ ok: true });
    expect(getAccessToken()).toBe("fresh-access");
    // The replay carries the new token, not the one that was rejected.
    expect(headersOf(adapter, 1).Authorization).toBe("Bearer fresh-access");
  });

  it("clears the session and redirects when the refresh fails", async () => {
    // jsdom's Location object is read-only and cannot be replaced, so the
    // redirect is observed through the "Not implemented: navigation" error
    // jsdom raises when the client calls location.assign.
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const { api, setTokens, getAccessToken, axios } = await loadApi();
    setTokens("stale-access", "refresh-1");
    jest.spyOn(axios, "post").mockRejectedValue(new Error("refresh rejected"));
    api.defaults.adapter = jest.fn(unauthorized) as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(errorSpy.mock.calls.flat().map(String).join(" ")).toContain(
      "Not implemented: navigation",
    );
    errorSpy.mockRestore();
  });

  it("does not attempt a refresh without a refresh token", async () => {
    const { api, axios } = await loadApi();
    const post = jest.spyOn(axios, "post");
    api.defaults.adapter = jest.fn(unauthorized) as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    expect(post).not.toHaveBeenCalled();
  });

  it("retries a 401 only once", async () => {
    const { api, setTokens, axios } = await loadApi();
    setTokens("stale-access", "refresh-1");
    jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "fresh", refresh_token: "r2" },
    } as never);
    const adapter = jest.fn(unauthorized);
    api.defaults.adapter = adapter as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    // Original + one replay; a loop here would hammer the API on every 401.
    expect(adapter).toHaveBeenCalledTimes(2);
  });

  it("passes non-401 failures through untouched", async () => {
    const { api, setTokens, axios } = await loadApi();
    setTokens("access-1", "refresh-1");
    const post = jest.spyOn(axios, "post");
    api.defaults.adapter = jest.fn((config: AxiosRequestConfig) => {
      const error = new Error("boom") as Error & {
        response?: { status: number };
        config?: AxiosRequestConfig;
      };
      error.response = { status: 500 };
      error.config = config;
      return Promise.reject(error);
    }) as never;

    await expect(api.get("/widgets")).rejects.toThrow("boom");
    expect(post).not.toHaveBeenCalled();
  });
});

describe("logging hygiene", () => {
  it("never writes a token value to the console", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    localStorage.setItem(ACCESS_KEY, "hydrated-secret");
    localStorage.setItem(REFRESH_KEY, "hydrated-refresh-secret");

    const { api, setTokens, clearTokens, axios } = await loadApi();
    setTokens("set-secret", "set-refresh-secret");

    jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "refreshed-secret", refresh_token: "r2-secret" },
    } as never);
    let attempt = 0;
    api.defaults.adapter = jest.fn((config: AxiosRequestConfig) => {
      attempt += 1;
      return attempt === 1 ? unauthorized(config) : ok(config);
    }) as never;
    await api.get("/widgets");
    clearTokens();

    const logged = logSpy.mock.calls.flat().join(" ");
    expect(logged).not.toContain("hydrated-secret");
    expect(logged).not.toContain("set-secret");
    expect(logged).not.toContain("refreshed-secret");
    expect(logged).not.toContain("r2-secret");
    // It still reports that the events happened.
    expect(logged).toContain("[ApiClient] TokenRefresh");
    logSpy.mockRestore();
  });

  it("reports a failed refresh without the token that failed", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const { api, setTokens, axios } = await loadApi();
    setTokens("access-secret", "refresh-secret");
    jest.spyOn(axios, "post").mockRejectedValue(new Error("nope"));
    api.defaults.adapter = jest.fn(unauthorized) as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    const logged = logSpy.mock.calls.flat().join(" ");
    expect(logged).toContain("[ApiClient] TokenRefresh { error: true }");
    expect(logged).not.toContain("refresh-secret");
    logSpy.mockRestore();
  });
});

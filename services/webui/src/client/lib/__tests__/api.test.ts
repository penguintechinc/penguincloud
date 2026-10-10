/**
 * API client interceptor tests.
 *
 * The interceptors are exercised through real requests against a stubbed
 * adapter rather than by reaching into axios internals, so the assertions
 * cover the chain a caller actually gets.
 *
 * The client no longer holds a refresh token: it lives only in the BFF's
 * HttpOnly cookie. These tests reflect that — the access token is memory-only
 * (never localStorage), and a 401 is recovered by POSTing to the BFF
 * `/api/ui/refresh` route (cookie-based), not by replaying a stored token.
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
 * Loads a fresh copy of the client. The module keeps the access token in a
 * module-scoped variable, so each scenario needs its own instance.
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

beforeEach(() => {
  localStorage.clear();
  // Clear any csrf cookie left over from another test.
  document.cookie = "csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  jest.restoreAllMocks();
});

describe("access token storage", () => {
  it("starts with no token", async () => {
    const { getAccessToken } = await loadApi();

    expect(getAccessToken()).toBeNull();
  });

  it("holds the access token in memory only — never localStorage", async () => {
    const { setAccessToken, getAccessToken } = await loadApi();

    setAccessToken("a");

    expect(getAccessToken()).toBe("a");
    // Nothing is written to localStorage: the old penguincloud_access_token /
    // penguincloud_refresh_token keys are gone for good.
    expect(localStorage.getItem("penguincloud_access_token")).toBeNull();
    expect(localStorage.getItem("penguincloud_refresh_token")).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("clears the access token", async () => {
    const { setAccessToken, clearAccessToken, getAccessToken } =
      await loadApi();
    setAccessToken("a");

    clearAccessToken();

    expect(getAccessToken()).toBeNull();
  });
});

describe("request interceptor", () => {
  it("attaches the bearer token", async () => {
    const { api, setAccessToken } = await loadApi();
    setAccessToken("access-1");
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

  it("refreshes on 401 via the BFF cookie route and replays the request", async () => {
    const { api, getAccessToken, axios } = await loadApi();
    document.cookie = "csrf=csrf-abc; path=/";

    const post = jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "fresh-access" },
    } as never);

    let attempt = 0;
    const adapter = jest.fn((config: AxiosRequestConfig) => {
      attempt += 1;
      return attempt === 1 ? unauthorized(config) : ok(config);
    });
    api.defaults.adapter = adapter as never;

    const response = await api.get("/widgets");

    // Refresh is a cookie-based POST to the BFF — no refresh token in the
    // body — carrying the double-submit CSRF header from the readable cookie.
    expect(post).toHaveBeenCalledWith(
      "/api/ui/refresh",
      {},
      { headers: { "X-CSRF-Token": "csrf-abc" } },
    );
    expect(response.data).toEqual({ ok: true });
    expect(getAccessToken()).toBe("fresh-access");
    // The replay carries the new token, not the one that was rejected.
    expect(headersOf(adapter, 1).Authorization).toBe("Bearer fresh-access");
  });

  it("sends an empty CSRF header when no csrf cookie is present", async () => {
    const { api, axios } = await loadApi();
    const post = jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "fresh-access" },
    } as never);
    let attempt = 0;
    api.defaults.adapter = jest.fn((config: AxiosRequestConfig) => {
      attempt += 1;
      return attempt === 1 ? unauthorized(config) : ok(config);
    }) as never;

    await api.get("/widgets");

    expect(post).toHaveBeenCalledWith(
      "/api/ui/refresh",
      {},
      { headers: { "X-CSRF-Token": "" } },
    );
  });

  it("clears the session and redirects when the refresh fails", async () => {
    // jsdom's Location object is read-only and cannot be replaced, so the
    // redirect is observed through the "Not implemented: navigation" error
    // jsdom raises when the client calls location.assign.
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const { api, setAccessToken, getAccessToken, axios } = await loadApi();
    setAccessToken("stale-access");
    jest.spyOn(axios, "post").mockRejectedValue(new Error("refresh rejected"));
    api.defaults.adapter = jest.fn(unauthorized) as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    expect(getAccessToken()).toBeNull();
    expect(errorSpy.mock.calls.flat().map(String).join(" ")).toContain(
      "Not implemented: navigation",
    );
    errorSpy.mockRestore();
  });

  it("retries a 401 only once", async () => {
    const { api, axios } = await loadApi();
    jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "fresh" },
    } as never);
    const adapter = jest.fn(unauthorized);
    api.defaults.adapter = adapter as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    // Original + one replay; a loop here would hammer the BFF on every 401.
    expect(adapter).toHaveBeenCalledTimes(2);
  });

  it("passes non-401 failures through untouched", async () => {
    const { api, axios } = await loadApi();
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

describe("refreshAccessToken", () => {
  it("stores and returns the access token from the BFF", async () => {
    const { refreshAccessToken, getAccessToken, axios } = await loadApi();
    jest
      .spyOn(axios, "post")
      .mockResolvedValue({ data: { access_token: "new-access" } } as never);

    const token = await refreshAccessToken();

    expect(token).toBe("new-access");
    expect(getAccessToken()).toBe("new-access");
  });

  it("returns null and stores nothing when the BFF sends no token", async () => {
    const { refreshAccessToken, getAccessToken, axios } = await loadApi();
    jest.spyOn(axios, "post").mockResolvedValue({ data: {} } as never);

    const token = await refreshAccessToken();

    expect(token).toBeNull();
    expect(getAccessToken()).toBeNull();
  });
});

describe("logging hygiene", () => {
  it("never writes a token value to the console", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    document.cookie = "csrf=csrf-secret; path=/";

    const { api, setAccessToken, clearAccessToken, axios } = await loadApi();
    setAccessToken("set-secret");

    jest.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "refreshed-secret" },
    } as never);
    let attempt = 0;
    api.defaults.adapter = jest.fn((config: AxiosRequestConfig) => {
      attempt += 1;
      return attempt === 1 ? unauthorized(config) : ok(config);
    }) as never;
    await api.get("/widgets");
    clearAccessToken();

    const logged = logSpy.mock.calls.flat().join(" ");
    expect(logged).not.toContain("set-secret");
    expect(logged).not.toContain("refreshed-secret");
    // It still reports that the events happened.
    expect(logged).toContain("[ApiClient] TokenRefresh");
    logSpy.mockRestore();
  });

  it("reports a failed refresh without the token that failed", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const { api, setAccessToken, axios } = await loadApi();
    setAccessToken("access-secret");
    jest.spyOn(axios, "post").mockRejectedValue(new Error("nope"));
    api.defaults.adapter = jest.fn(unauthorized) as never;

    await expect(api.get("/widgets")).rejects.toBeDefined();

    const logged = logSpy.mock.calls.flat().join(" ");
    expect(logged).toContain("[ApiClient] TokenRefresh { error: true }");
    expect(logged).not.toContain("access-secret");
    logSpy.mockRestore();
    errorSpy.mockRestore();
  });
});

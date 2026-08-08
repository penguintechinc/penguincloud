/**
 * Typed portal client.
 *
 * Most of this module's value is at COMPILE time — a wrong path or method is
 * a type error, which no runtime test can observe. What is tested here is
 * the runtime behaviour that types cannot express: path interpolation, the
 * base-prefix rule, and the fact that requests are delegated to the shared
 * axios instance rather than a second one with its own auth handling.
 */

import { buildPath, portal } from "../portal";
import { queryKeys } from "../keys";
import api from "../../lib/api";

jest.mock("../../lib/api", () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}));

const mockedApi = api as unknown as {
  get: jest.Mock;
  post: jest.Mock;
  put: jest.Mock;
  delete: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockedApi.get.mockResolvedValue({ data: { ok: true } });
  mockedApi.post.mockResolvedValue({ data: { ok: true } });
  mockedApi.put.mockResolvedValue({ data: { ok: true } });
  mockedApi.delete.mockResolvedValue({ data: { ok: true } });
});

describe("buildPath", () => {
  it("substitutes a single placeholder", () => {
    expect(buildPath("/api/v1/tenants/{tenant_id}", { tenant_id: 42 })).toBe(
      "/api/v1/tenants/42",
    );
  });

  it("substitutes every placeholder in a nested path", () => {
    expect(
      buildPath("/api/v1/products/{product_id}/tenants/{tenant_id}/map", {
        product_id: 3,
        tenant_id: 9,
      }),
    ).toBe("/api/v1/products/3/tenants/9/map");
  });

  it("URL-encodes values so they cannot change the endpoint", () => {
    // A slug or external id may legitimately contain a slash or a query
    // character; interpolated raw, either would redirect the call to a
    // different endpoint than the one the caller named.
    expect(buildPath("/api/v1/tenants/{tenant_id}", { tenant_id: "a/b" })).toBe(
      "/api/v1/tenants/a%2Fb",
    );
    expect(
      buildPath("/api/v1/tenants/{tenant_id}", { tenant_id: "x?y=1" }),
    ).toBe("/api/v1/tenants/x%3Fy%3D1");
  });

  it("throws on a missing parameter rather than sending {placeholder}", () => {
    // Silently requesting a literal "{tenant_id}" would 404 far from the
    // bug, and in the worst case match a catch-all route.
    expect(() => buildPath("/api/v1/tenants/{tenant_id}", {})).toThrow(
      /Missing path parameter "tenant_id"/,
    );
  });

  it("leaves a path with no placeholders untouched", () => {
    expect(buildPath("/api/v1/tenants")).toBe("/api/v1/tenants");
  });
});

describe("portal request helpers", () => {
  it("strips the /api/v1 prefix already carried by the axios baseURL", async () => {
    // The axios instance is created with baseURL "/api/v1" while the OpenAPI
    // document keys paths absolutely. Without the strip, every call would
    // request /api/v1/api/v1/...
    await portal.get("/api/v1/tenants");

    expect(mockedApi.get).toHaveBeenCalledWith("/tenants", {
      params: undefined,
    });
  });

  it("interpolates path params before dispatching", async () => {
    await portal.get("/api/v1/tenants/{tenant_id}", { path: { tenant_id: 5 } });

    expect(mockedApi.get).toHaveBeenCalledWith("/tenants/5", {
      params: undefined,
    });
  });

  it("passes query parameters through", async () => {
    await portal.get("/api/v1/products", { query: { tenant_id: 4 } });

    expect(mockedApi.get).toHaveBeenCalledWith("/products", {
      params: { tenant_id: 4 },
    });
  });

  it("sends a body on post", async () => {
    await portal.post("/api/v1/tenants", { name: "Acme", slug: "acme" });

    expect(mockedApi.post).toHaveBeenCalledWith(
      "/tenants",
      { name: "Acme", slug: "acme" },
      { params: undefined },
    );
  });

  it("sends a body on put with interpolated params", async () => {
    await portal.put(
      "/api/v1/tenants/{tenant_id}",
      { display_name: "Renamed" },
      { path: { tenant_id: 11 } },
    );

    expect(mockedApi.put).toHaveBeenCalledWith(
      "/tenants/11",
      { display_name: "Renamed" },
      { params: undefined },
    );
  });

  it("issues a delete", async () => {
    await portal.delete("/api/v1/tenants/{tenant_id}", {
      path: { tenant_id: 2 },
    });

    expect(mockedApi.delete).toHaveBeenCalledWith("/tenants/2", {
      params: undefined,
    });
  });

  it("unwraps the axios envelope and returns the body", async () => {
    mockedApi.get.mockResolvedValue({ data: { tenants: [], count: 0 } });

    const result = await portal.get("/api/v1/tenants");

    expect(result).toEqual({ tenants: [], count: 0 });
  });

  it("delegates to the shared axios instance, not a second client", async () => {
    // The shared instance owns token attachment, 401 refresh and the tenant
    // header. A second client would give the app two auth paths that can
    // disagree, and the generated one would be the less-exercised of them.
    await portal.get("/api/v1/tenants");

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  it("leaves a path outside the /api/v1 prefix alone", async () => {
    // The health probes are documented at the root, not under /api/v1.
    // Stripping unconditionally would turn /healthz into a request for the
    // baseURL itself.
    await portal.get("/healthz");

    expect(mockedApi.get).toHaveBeenCalledWith("/healthz", {
      params: undefined,
    });
  });

  it("accepts a put with no options argument", async () => {
    await portal.put("/api/v1/users/me", { full_name: "New Name" });

    expect(mockedApi.put).toHaveBeenCalledWith(
      "/users/me",
      { full_name: "New Name" },
      { params: undefined },
    );
  });

  it("accepts a post with no body and no options", async () => {
    await portal.post("/api/v1/auth/logout");

    expect(mockedApi.post).toHaveBeenCalledWith("/auth/logout", undefined, {
      params: undefined,
    });
  });

  it("accepts a delete with no options argument", async () => {
    // Every documented DELETE takes a path parameter, so calling one with
    // no options is a caller error — and it must surface as the explicit
    // "missing path parameter" throw rather than dispatching a request for
    // a literal "{key_id}". This is the only way to reach the defaulted
    // options branch on delete.
    await expect(
      portal.delete("/api/v1/users/api-keys/{key_id}"),
    ).rejects.toThrow(/Missing path parameter "key_id"/);

    expect(mockedApi.delete).not.toHaveBeenCalled();
  });

  it("propagates request failures to the caller", async () => {
    // Errors must reach the axios interceptors and then the caller; a
    // helper that swallowed them would hide 401s from the refresh logic.
    mockedApi.get.mockRejectedValue(new Error("network down"));

    await expect(portal.get("/api/v1/tenants")).rejects.toThrow("network down");
  });
});

describe("queryKeys.endpoint", () => {
  it("builds a tenant-scoped key for a documented path", () => {
    expect(queryKeys.endpoint("/api/v1/tenants", 7)).toEqual([
      "api",
      "endpoint",
      "/api/v1/tenants",
      7,
      null,
    ]);
  });

  it("distinguishes the same path across different tenants", () => {
    // The property that matters: without the tenant id in the key, a tenant
    // switch serves the previous tenant's cached rows.
    const a = queryKeys.endpoint("/api/v1/tenants", 1);
    const b = queryKeys.endpoint("/api/v1/tenants", 2);

    expect(a).not.toEqual(b);
  });

  it("distinguishes the same path under different params", () => {
    const first = queryKeys.endpoint("/api/v1/products", 1, { page: 1 });
    const second = queryKeys.endpoint("/api/v1/products", 1, { page: 2 });

    expect(first).not.toEqual(second);
  });

  it("treats an absent param bag as a stable null, not undefined", () => {
    // undefined is dropped by structural comparison in some cache
    // implementations, which would collide with a key that had params.
    expect(queryKeys.endpoint("/api/v1/tenants", 1)).toEqual([
      "api",
      "endpoint",
      "/api/v1/tenants",
      1,
      null,
    ]);
  });

  it("nests under the shared root so a global invalidation reaches it", () => {
    const key = queryKeys.endpoint("/api/v1/tenants", 1);
    expect(key[0]).toBe(queryKeys.all()[0]);
  });
});

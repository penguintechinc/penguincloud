/**
 * Tests for the API resource wrappers.
 *
 * These are thin bindings over the axios client, so what matters is that each
 * one hits the right path with the right params and unwraps the right part of
 * the response. The client itself is mocked.
 */

import api from "../../lib/api";
import { proxyRequestUrl } from "../portalPaths";
import { usersApi } from "../resources/users";
import { tenantsApi } from "../resources/tenants";
import { productsApi, discoveryApi, proxyApi } from "../resources/products";
import { dashboardApi, auditApi } from "../resources/dashboard";
import { helloApi } from "../resources/platform";

jest.mock("../../lib/api");

const mockApi = api as unknown as {
  get: jest.Mock;
  post: jest.Mock;
  put: jest.Mock;
  delete: jest.Mock;
  request: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: {} });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.request.mockResolvedValue({ data: {} });
});

describe("usersApi", () => {
  it("pages the user list", async () => {
    mockApi.get.mockResolvedValue({ data: { items: [], total: 0 } });
    await usersApi.list(2, 50);
    expect(mockApi.get).toHaveBeenCalledWith("/users", {
      params: { page: 2, per_page: 50 },
    });
  });

  it("defaults to the first page", async () => {
    await usersApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/users", {
      params: { page: 1, per_page: 20 },
    });
  });

  it("reads, creates, updates and deletes", async () => {
    await usersApi.get(4);
    expect(mockApi.get).toHaveBeenCalledWith("/users/4");

    await usersApi.create({
      email: "a@b.test",
      password: "pw",
      full_name: "A",
      role: "viewer",
    });
    expect(mockApi.post).toHaveBeenCalledWith("/users", expect.any(Object));

    await usersApi.update(4, { full_name: "B" });
    expect(mockApi.put).toHaveBeenCalledWith("/users/4", { full_name: "B" });

    await usersApi.delete(4);
    expect(mockApi.delete).toHaveBeenCalledWith("/users/4");
  });
});

describe("tenantsApi", () => {
  it("omits include_children unless asked", async () => {
    await tenantsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/tenants", { params: undefined });
  });

  it("requests the subtree when asked", async () => {
    await tenantsApi.list(true);
    expect(mockApi.get).toHaveBeenCalledWith("/tenants", {
      params: { include_children: true },
    });
  });

  it("covers the single-tenant lifecycle", async () => {
    await tenantsApi.get(1);
    expect(mockApi.get).toHaveBeenCalledWith("/tenants/1");

    await tenantsApi.create({ name: "N", slug: "n" });
    expect(mockApi.post).toHaveBeenCalledWith("/tenants", {
      name: "N",
      slug: "n",
    });

    await tenantsApi.update(1, { plan: "free" });
    expect(mockApi.put).toHaveBeenCalledWith("/tenants/1", { plan: "free" });

    await tenantsApi.delete(1);
    expect(mockApi.delete).toHaveBeenCalledWith("/tenants/1");
  });

  it("switches scope through the switch endpoint", async () => {
    await tenantsApi.switchTenant(2);
    expect(mockApi.post).toHaveBeenCalledWith("/tenants/2/switch");
  });

  it("manages membership", async () => {
    await tenantsApi.getMembers(2);
    expect(mockApi.get).toHaveBeenCalledWith("/tenants/2/members");

    await tenantsApi.addMember(2, 9, "admin");
    expect(mockApi.post).toHaveBeenCalledWith("/tenants/2/members", {
      user_id: 9,
      role: "admin",
    });

    await tenantsApi.updateMember(2, 9, "viewer");
    expect(mockApi.put).toHaveBeenCalledWith("/tenants/2/members/9", {
      role: "viewer",
    });

    await tenantsApi.removeMember(2, 9);
    expect(mockApi.delete).toHaveBeenCalledWith("/tenants/2/members/9");
  });

  it("reads usage counters", async () => {
    await tenantsApi.getUsage(2);
    expect(mockApi.get).toHaveBeenCalledWith("/tenants/2/usage");
  });
});

describe("productsApi", () => {
  it("scopes the connection list by tenant", async () => {
    await productsApi.list(3);
    expect(mockApi.get).toHaveBeenCalledWith("/products", {
      params: { tenant_id: 3 },
    });
  });

  it("covers catalogue, lifecycle, test, health and schema", async () => {
    await productsApi.types();
    expect(mockApi.get).toHaveBeenCalledWith("/products/types");

    await productsApi.get(5);
    expect(mockApi.get).toHaveBeenCalledWith("/products/5");

    await productsApi.register({ base_url: "https://x" });
    expect(mockApi.post).toHaveBeenCalledWith("/products", {
      base_url: "https://x",
    });

    await productsApi.update(5, { base_url: "https://y" });
    expect(mockApi.put).toHaveBeenCalledWith("/products/5", {
      base_url: "https://y",
    });

    await productsApi.delete(5);
    expect(mockApi.delete).toHaveBeenCalledWith("/products/5");

    await productsApi.test(5);
    expect(mockApi.post).toHaveBeenCalledWith("/products/5/test");

    await productsApi.health(5);
    expect(mockApi.get).toHaveBeenCalledWith("/products/5/health");

    await productsApi.schema(5);
    expect(mockApi.get).toHaveBeenCalledWith("/products/5/schema");
  });
});

describe("discoveryApi", () => {
  it("scans, lists and accepts", async () => {
    await discoveryApi.scan(1, ["10.0.0.0/24"]);
    expect(mockApi.post).toHaveBeenCalledWith("/discovery/scan", {
      tenant_id: 1,
      ranges: ["10.0.0.0/24"],
    });

    await discoveryApi.results(1);
    expect(mockApi.get).toHaveBeenCalledWith("/discovery/results", {
      params: { tenant_id: 1 },
    });

    await discoveryApi.accept(8, 1, { display_name: "X" });
    expect(mockApi.post).toHaveBeenCalledWith("/discovery/accept/8", {
      tenant_id: 1,
      display_name: "X",
    });
  });

  it("accepts without extra fields", async () => {
    await discoveryApi.accept(8, 1);
    expect(mockApi.post).toHaveBeenCalledWith("/discovery/accept/8", {
      tenant_id: 1,
    });
  });
});

describe("proxyApi", () => {
  it("forwards method, path and body to the product proxy", async () => {
    await proxyApi.request(6, "POST", "nodes", { name: "n1" });
    // The URL comes from `proxyRequestUrl`, which `portalPaths.test.ts` ties
    // to the rule the portal registers. Spelling it literally here is how the
    // suite previously pinned `/proxy/6/nodes` — a route that does not exist.
    expect(mockApi.request).toHaveBeenCalledWith({
      method: "POST",
      url: proxyRequestUrl(6, "nodes"),
      data: { name: "n1" },
    });
  });
});

describe("dashboardApi", () => {
  it("scopes overview, health, activity and alerts by tenant", async () => {
    await dashboardApi.overview(1);
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/overview", {
      params: { tenant_id: 1 },
    });

    await dashboardApi.health(1);
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/health", {
      params: { tenant_id: 1 },
    });

    await dashboardApi.activity(1);
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/activity", {
      params: { tenant_id: 1, limit: 20 },
    });

    await dashboardApi.alerts(1);
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/alerts", {
      params: { tenant_id: 1 },
    });
  });

  it("honours an explicit activity limit", async () => {
    await dashboardApi.activity(1, 5);
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/activity", {
      params: { tenant_id: 1, limit: 5 },
    });
  });

  it("unwraps the rollup envelope from the TENANT-scoped route", async () => {
    // The URL is the fix, not decoration: this called `/dashboard/rollup` with
    // a tenant_id query parameter, and the portal registers no such route — it
    // is `/api/v1/tenants/{tenant_id}/dashboard/rollup` (`tenants.py:901`). It
    // had never worked; `test_webui_portal_paths.py` now binds it to url_map.
    mockApi.get.mockResolvedValue({
      data: { rollup: [{ tenant_id: "t1", tenant_name: "T", products: [] }] },
    });

    const rows = await dashboardApi.rollup(1);

    expect(mockApi.get).toHaveBeenCalledWith("/tenants/1/dashboard/rollup");
    expect(rows).toHaveLength(1);
  });

  it("refuses to report a missing rollup key as no customers", async () => {
    // `rollup` is a required field of `RollupResponse`, so an empty subtree
    // arrives as `{"rollup": []}`. A provider seeing an empty customer matrix
    // has no way to tell that from a response nobody understood.
    mockApi.get.mockResolvedValue({ data: {} });

    await expect(dashboardApi.rollup(1)).rejects.toThrow(/no "rollup" key/);
  });

  it("still reports a genuinely empty subtree as empty", async () => {
    mockApi.get.mockResolvedValue({ data: { rollup: [] } });

    await expect(dashboardApi.rollup(1)).resolves.toEqual([]);
  });
});

describe("auditApi", () => {
  it("pages audit logs per tenant", async () => {
    await auditApi.logs(1, 3, 25);
    expect(mockApi.get).toHaveBeenCalledWith("/audit/logs", {
      params: { tenant_id: 1, page: 3, per_page: 25 },
    });
  });

  it("defaults paging", async () => {
    await auditApi.logs(1);
    expect(mockApi.get).toHaveBeenCalledWith("/audit/logs", {
      params: { tenant_id: 1, page: 1, per_page: 50 },
    });
  });

  it("requests a blob for CSV export and JSON otherwise", async () => {
    await auditApi.export(1, "csv");
    expect(mockApi.get).toHaveBeenCalledWith("/audit/export", {
      params: { tenant_id: 1, format: "csv", limit: 1000 },
      responseType: "blob",
    });

    await auditApi.export(1);
    expect(mockApi.get).toHaveBeenCalledWith("/audit/export", {
      params: { tenant_id: 1, format: "json", limit: 1000 },
      responseType: "json",
    });
  });
});

describe("platform endpoints", () => {
  it("reads the hello routes", async () => {
    await helloApi.get();
    expect(mockApi.get).toHaveBeenCalledWith("/hello");

    await helloApi.getProtected();
    expect(mockApi.get).toHaveBeenCalledWith("/hello/protected");
  });
});

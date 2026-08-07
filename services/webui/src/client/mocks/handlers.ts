/**
 * MSW request handlers.
 *
 * Endpoint shapes follow task-2B-brief: tenants (with `include_children`),
 * the switch endpoint, the provider rollup, and the auth surface — plus the
 * `/api/ui/login` BFF adapter the shared-library login page posts to.
 */

import { http, HttpResponse } from "msw";
import {
  MOCK_TENANTS,
  MOCK_DASHBOARD_ROLLUP,
  MOCK_PRODUCTS_BY_TENANT,
  PROVIDER_ONE,
  generateMockToken,
} from "./fixtures";

const API_BASE = "/api/v1";

const MOCK_USER = {
  id: 1,
  email: "admin@penguincloud.test",
  full_name: "Ada Admin",
  role: "admin",
  is_active: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: null,
  home_tenant_id: PROVIDER_ONE,
};

function tokenPair(tenant: number) {
  return {
    access_token: generateMockToken({
      sub: "user-1",
      tenant,
      home_tenant: PROVIDER_ONE,
      roles: ["Admin"],
      scope: ["tenants:read", "tenants:manage", "products:read"],
    }),
    refresh_token: generateMockToken({ sub: "user-1", tenant }),
  };
}

export const handlers = [
  /**
   * GET /api/v1/tenants?include_children=true
   * Flat roster; with include_children each provider also carries its
   * customers inline.
   */
  http.get(`${API_BASE}/tenants`, ({ request }) => {
    const includeChildren =
      new URL(request.url).searchParams.get("include_children") === "true";

    if (includeChildren) {
      return HttpResponse.json({
        tenants: MOCK_TENANTS.map((t) => ({
          ...t,
          children: MOCK_TENANTS.filter((c) => c.parent_tenant_id === t.id),
        })),
        count: MOCK_TENANTS.length,
      });
    }

    return HttpResponse.json({
      tenants: MOCK_TENANTS,
      count: MOCK_TENANTS.length,
    });
  }),

  /**
   * POST /api/v1/tenants/:id/switch
   * Re-issues an access token whose claims name the new active tenant.
   */
  http.post(`${API_BASE}/tenants/:id/switch`, ({ params }) => {
    const tenantId = Number(params.id);
    const tenant = MOCK_TENANTS.find((t) => t.id === tenantId);

    if (!tenant) {
      return HttpResponse.json({ error: "Tenant not found" }, { status: 404 });
    }

    return HttpResponse.json({
      ...tokenPair(tenantId),
      tenant,
      tenant_role: "admin",
    });
  }),

  /**
   * GET /api/v1/dashboard/rollup?tenant_id=
   * Per-customer × per-product status for the requesting provider org. Row
   * shape per task-2B-brief: {tenant_id, tenant_name, products: [{
   * connection_id, product, status}]}.
   */
  http.get(`${API_BASE}/dashboard/rollup`, ({ request }) => {
    const tenantId = Number(
      new URL(request.url).searchParams.get("tenant_id") ?? NaN,
    );

    if (Number.isNaN(tenantId)) {
      return HttpResponse.json({ rollup: MOCK_DASHBOARD_ROLLUP });
    }

    // Scoped to the caller's own customers — a provider must not see another
    // provider's subtree, which is what the delegated-admin check enforces.
    const customerIds = MOCK_TENANTS.filter(
      (t) => t.parent_tenant_id === tenantId,
    ).map((t) => t.id);

    return HttpResponse.json({
      rollup: MOCK_DASHBOARD_ROLLUP.filter((row) =>
        customerIds.includes(row.tenant_id),
      ),
    });
  }),

  /** GET /api/v1/dashboard/overview */
  http.get(`${API_BASE}/dashboard/overview`, ({ request }) => {
    const tenantId = Number(
      new URL(request.url).searchParams.get("tenant_id") ?? NaN,
    );
    const products = MOCK_PRODUCTS_BY_TENANT[tenantId] ?? [];

    return HttpResponse.json({
      tenant: { id: tenantId, name: "Mock Tenant", plan: "enterprise" },
      stats: {
        total_products: products.length,
        total_members: 4,
        health: {
          healthy: products.filter((p) => p.health_status === "healthy").length,
          degraded: products.filter((p) => p.health_status === "degraded")
            .length,
          unhealthy: 0,
          unknown: 0,
        },
        categories: { infrastructure: products.length },
      },
      products,
    });
  }),

  /** GET /api/v1/dashboard/activity */
  http.get(`${API_BASE}/dashboard/activity`, () =>
    HttpResponse.json({
      activity: [
        {
          id: 1,
          user_id: 1,
          action: "tenant.switch",
          resource_type: "tenant",
          resource_id: "11",
          tenant_id: PROVIDER_ONE,
          product_connection_id: null,
          ip_address: "10.0.0.1",
          created_at: "2026-08-01T12:00:00Z",
        },
      ],
      count: 1,
    }),
  ),

  /** GET /api/v1/dashboard/health */
  http.get(`${API_BASE}/dashboard/health`, () =>
    HttpResponse.json({ status: "healthy" }),
  ),

  /**
   * POST /api/ui/login
   * BFF adapter endpoint consumed by the shared-library login page. Mirrors
   * the translation performed by src/server/authAdapter.ts.
   */
  http.post("/api/ui/login", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      email?: string;
      password?: string;
    };

    if (!body.email || !body.password) {
      return HttpResponse.json(
        {
          success: false,
          error: "Email and password are required",
          errorCode: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    // Any password but "wrong" authenticates, so the smoke test can exercise
    // the failure path without a second fixture user.
    if (body.password === "wrong") {
      return HttpResponse.json(
        {
          success: false,
          error: "Invalid email or password",
          errorCode: "AUTH_FAILED",
        },
        { status: 401 },
      );
    }

    const tokens = tokenPair(PROVIDER_ONE);
    return HttpResponse.json({
      success: true,
      token: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user: {
        id: String(MOCK_USER.id),
        email: body.email,
        name: MOCK_USER.full_name,
        roles: [MOCK_USER.role],
      },
    });
  }),

  /** GET /api/v1/auth/me — hydrates the auth store after login and on reload. */
  http.get(`${API_BASE}/auth/me`, () => HttpResponse.json(MOCK_USER)),

  /** POST /api/v1/auth/login — direct API contract, no `success` envelope. */
  http.post(`${API_BASE}/auth/login`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      email?: string;
      password?: string;
    };

    if (!body.email || !body.password) {
      return HttpResponse.json(
        { error: "Email and password required" },
        { status: 400 },
      );
    }

    return HttpResponse.json({
      ...tokenPair(PROVIDER_ONE),
      token_type: "Bearer",
      expires_in: 3600,
      user: MOCK_USER,
    });
  }),

  /** POST /api/v1/auth/refresh */
  http.post(`${API_BASE}/auth/refresh`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      refresh_token?: string;
    };

    if (!body.refresh_token) {
      return HttpResponse.json(
        { error: "Refresh token required" },
        { status: 400 },
      );
    }

    return HttpResponse.json(tokenPair(PROVIDER_ONE));
  }),

  /** POST /api/v1/auth/logout */
  http.post(`${API_BASE}/auth/logout`, () =>
    HttpResponse.json({ success: true }),
  ),

  /** GET /api/v1/products?tenant_id= */
  http.get(`${API_BASE}/products`, ({ request }) => {
    const tenantId = Number(
      new URL(request.url).searchParams.get("tenant_id") ?? NaN,
    );
    const products = MOCK_PRODUCTS_BY_TENANT[tenantId] ?? [];
    return HttpResponse.json({ products, count: products.length });
  }),

  /**
   * GET /api/v1/status
   * Polled by the shared-library AppConsoleVersion banner in the footer; the
   * whole shell logs a failed request on every page without it.
   */
  http.get(`${API_BASE}/status`, () =>
    HttpResponse.json({ version: "1.0.0", build_epoch: 1754500000 }),
  ),

  /** GET /api/v1/audit/logs */
  http.get(`${API_BASE}/audit/logs`, () =>
    HttpResponse.json({ logs: [], total: 0 }),
  ),

  /** GET /api/v1/users */
  http.get(`${API_BASE}/users`, () =>
    HttpResponse.json({
      items: [MOCK_USER],
      total: 1,
      page: 1,
      per_page: 20,
      pages: 1,
    }),
  ),
];

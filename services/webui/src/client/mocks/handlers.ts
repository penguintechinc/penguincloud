/**
 * MSW request handlers for mocked API endpoints.
 * Matches task-2B-brief endpoint shapes for tenants, switch, dashboard rollup, and auth.
 */

import { http, HttpResponse } from "msw";
import {
  MOCK_TENANTS,
  MOCK_DASHBOARD_ROLLUP,
  generateMockToken,
  type MockTenant,
} from "./fixtures";

const API_BASE = "/api/v1";

export const handlers = [
  /**
   * GET /api/v1/tenants?include_children=true
   * Returns hierarchical tenant tree (provider org + customer tenants).
   */
  http.get(`${API_BASE}/tenants`, ({ request }) => {
    const url = new URL(request.url);
    const includeChildren = url.searchParams.get("include_children") === "true";

    if (includeChildren) {
      // Return full hierarchy
      return HttpResponse.json({
        tenants: MOCK_TENANTS.map((t) => ({
          ...t,
          children: MOCK_TENANTS.filter(
            (child) => child.parent_tenant_id === t.id,
          ),
        })),
      });
    }

    // Return flat list (caller's perspective)
    return HttpResponse.json({
      tenants: MOCK_TENANTS,
    });
  }),

  /**
   * POST /api/v1/tenants/:id/switch
   * Switches active tenant, re-issues access token with updated claims.
   */
  http.post(`${API_BASE}/tenants/:id/switch`, async ({ params }) => {
    const tenantId = params.id as string;

    const tenant = MOCK_TENANTS.find((t) => t.id === tenantId);
    if (!tenant) {
      return HttpResponse.json({ error: "Tenant not found" }, { status: 404 });
    }

    // Generate re-issued token with updated tenant claim
    const newToken = generateMockToken({
      tenant: tenantId,
      home_tenant: "provider-1", // Simulate provider context
    });

    return HttpResponse.json({
      access_token: newToken,
      refresh_token: generateMockToken({
        sub: "user-1",
        tenant: tenantId,
        home_tenant: "provider-1",
      }),
      tenant: tenant as MockTenant,
      tenant_role: "maintainer", // Simulated role
    });
  }),

  /**
   * GET /api/v1/dashboard/rollup
   * Returns per-tenant × per-product health status matrix for provider scope.
   */
  http.get(`${API_BASE}/dashboard/rollup`, () => {
    return HttpResponse.json({
      rollup: MOCK_DASHBOARD_ROLLUP,
    });
  }),

  /**
   * POST /api/v1/auth/login
   * Authenticates user, returns access + refresh tokens.
   */
  http.post(`${API_BASE}/auth/login`, async ({ request }) => {
    try {
      const body = (await request.json()) as {
        email?: string;
        password?: string;
      };

      if (!body.email || !body.password) {
        return HttpResponse.json(
          { error: "Email and password required" },
          { status: 400 },
        );
      }

      // Mock: accept any email/password combo for testing
      const accessToken = generateMockToken({
        sub: "user-1",
        tenant: "provider-1",
        home_tenant: "provider-1",
        roles: ["Admin"],
        scope: ["tenants:read", "products:read", "tenants:manage"],
      });

      const refreshToken = generateMockToken({
        sub: "user-1",
        tenant: "provider-1",
        home_tenant: "provider-1",
      });

      return HttpResponse.json({
        access_token: accessToken,
        refresh_token: refreshToken,
        user: {
          id: "user-1",
          email: body.email,
          full_name: "Test User",
          role: "admin",
        },
      });
    } catch {
      return HttpResponse.json({ error: "Invalid request" }, { status: 400 });
    }
  }),

  /**
   * POST /api/v1/auth/refresh
   * Refreshes access token using refresh token.
   */
  http.post(`${API_BASE}/auth/refresh`, async ({ request }) => {
    try {
      const body = (await request.json()) as { refresh_token?: string };

      if (!body.refresh_token) {
        return HttpResponse.json(
          { error: "Refresh token required" },
          { status: 400 },
        );
      }

      const newAccessToken = generateMockToken({
        sub: "user-1",
        tenant: "provider-1",
        home_tenant: "provider-1",
        roles: ["Admin"],
        scope: ["tenants:read", "products:read"],
      });

      return HttpResponse.json({
        access_token: newAccessToken,
      });
    } catch {
      return HttpResponse.json({ error: "Invalid request" }, { status: 400 });
    }
  }),

  /**
   * POST /api/v1/auth/logout
   * Clears session/tokens.
   */
  http.post(`${API_BASE}/auth/logout`, () => {
    return HttpResponse.json({ success: true });
  }),

  /**
   * GET /api/v1/products
   * Returns product connections for a tenant.
   */
  http.get(`${API_BASE}/products`, ({ request }) => {
    const url = new URL(request.url);
    const tenantId = url.searchParams.get("tenant_id");

    // Mock: return different products per tenant
    const products = [];

    if (tenantId === "customer-1") {
      products.push(
        {
          id: "conn-gough-1",
          product_type: "gough",
          display_name: "Gough (Prod)",
          status: "healthy",
        },
        {
          id: "conn-nest-1",
          product_type: "nest",
          display_name: "Nest (Prod)",
          status: "healthy",
        },
        {
          id: "conn-waddleai-1",
          product_type: "waddleai",
          display_name: "WaddleAI (Prod)",
          status: "degraded",
        },
      );
    } else if (tenantId === "customer-3") {
      products.push(
        {
          id: "conn-tobogganing-1",
          product_type: "tobogganing",
          display_name: "Tobogganing (Platform)",
          status: "healthy",
        },
        {
          id: "conn-waddlebot-1",
          product_type: "waddlebot",
          display_name: "WaddleBot (Platform)",
          status: "healthy",
        },
      );
    }

    return HttpResponse.json({
      products,
    });
  }),
];

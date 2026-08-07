/**
 * Mock data fixtures for testing and MSW-mocked dev mode.
 * 2-provider org with 4 customer tenants, realistic shape matching task-2B API.
 */

export interface MockTenant {
  id: string;
  name: string;
  display_name?: string;
  slug: string;
  kind: "provider" | "customer";
  parent_tenant_id?: string | null;
  depth: number;
  plan?: string;
  created_at: string;
  user_role?: string;
}

export interface MockProduct {
  id: string;
  product_type: string;
  display_name: string;
  status: "healthy" | "degraded" | "down" | "unknown";
}

export interface MockTenantWithProducts extends MockTenant {
  products?: MockProduct[];
}

export interface MockDashboardRollup {
  tenant_id: string;
  tenant_name: string;
  products: Array<{
    connection_id: string;
    product: string;
    status: "healthy" | "degraded" | "down" | "unknown";
  }>;
}

export const MOCK_TENANTS: MockTenant[] = [
  // Provider orgs
  {
    id: "provider-1",
    name: "Acme Corp",
    display_name: "Acme Corp (Provider)",
    slug: "acme-corp",
    kind: "provider",
    parent_tenant_id: null,
    depth: 0,
    plan: "enterprise",
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "provider-2",
    name: "TechVision",
    display_name: "TechVision (Provider)",
    slug: "techvision",
    kind: "provider",
    parent_tenant_id: null,
    depth: 0,
    plan: "enterprise",
    created_at: "2025-02-01T00:00:00Z",
  },
  // Customer tenants under provider-1
  {
    id: "customer-1",
    name: "Acme Production",
    display_name: "Acme Production",
    slug: "acme-prod",
    kind: "customer",
    parent_tenant_id: "provider-1",
    depth: 1,
    plan: "professional",
    created_at: "2025-03-01T00:00:00Z",
  },
  {
    id: "customer-2",
    name: "Acme Staging",
    display_name: "Acme Staging",
    slug: "acme-stage",
    kind: "customer",
    parent_tenant_id: "provider-1",
    depth: 1,
    plan: "professional",
    created_at: "2025-03-05T00:00:00Z",
  },
  // Customer tenants under provider-2
  {
    id: "customer-3",
    name: "TechVision Platform",
    display_name: "TechVision Platform",
    slug: "techvision-platform",
    kind: "customer",
    parent_tenant_id: "provider-2",
    depth: 1,
    plan: "professional",
    created_at: "2025-04-01T00:00:00Z",
  },
  {
    id: "customer-4",
    name: "TechVision Research",
    display_name: "TechVision Research",
    slug: "techvision-research",
    kind: "customer",
    parent_tenant_id: "provider-2",
    depth: 1,
    plan: "free",
    created_at: "2025-04-10T00:00:00Z",
  },
];

export const MOCK_DASHBOARD_ROLLUP: MockDashboardRollup[] = [
  {
    tenant_id: "customer-1",
    tenant_name: "Acme Production",
    products: [
      {
        connection_id: "conn-gough-1",
        product: "gough",
        status: "healthy",
      },
      {
        connection_id: "conn-nest-1",
        product: "nest",
        status: "healthy",
      },
      {
        connection_id: "conn-waddleai-1",
        product: "waddleai",
        status: "degraded",
      },
    ],
  },
  {
    tenant_id: "customer-2",
    tenant_name: "Acme Staging",
    products: [
      {
        connection_id: "conn-gough-2",
        product: "gough",
        status: "healthy",
      },
      {
        connection_id: "conn-nest-2",
        product: "nest",
        status: "healthy",
      },
    ],
  },
  {
    tenant_id: "customer-3",
    tenant_name: "TechVision Platform",
    products: [
      {
        connection_id: "conn-tobogganing-1",
        product: "tobogganing",
        status: "healthy",
      },
      {
        connection_id: "conn-waddlebot-1",
        product: "waddlebot",
        status: "healthy",
      },
    ],
  },
  {
    tenant_id: "customer-4",
    tenant_name: "TechVision Research",
    products: [
      {
        connection_id: "conn-elder-1",
        product: "elder",
        status: "healthy",
      },
    ],
  },
];

/**
 * Mock token payload (simplified JWT content).
 */
export interface MockTokenPayload {
  sub: string;
  tenant: string;
  home_tenant: string;
  roles: string[];
  scope: string[];
  iat: number;
  exp: number;
}

/**
 * Generate a mock JWT token (base64-encoded JSON, no real signature).
 * DO NOT use in production; for testing only.
 */
export function generateMockToken(payload: Partial<MockTokenPayload>): string {
  const defaults: MockTokenPayload = {
    sub: "user-1",
    tenant: "provider-1",
    home_tenant: "provider-1",
    roles: ["Admin"],
    scope: ["tenants:read", "products:read"],
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
  };

  const finalPayload = { ...defaults, ...payload };

  // Simplified JWT: header.payload.signature (signature is fake)
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(finalPayload));
  const signature = "fake_signature";

  return `${header}.${body}.${signature}`;
}

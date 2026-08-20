/**
 * Mock data fixtures for jest and the MSW-mocked dev/E2E mode.
 *
 * Two provider orgs with two customer tenants each. Ids are numbers because
 * that is what `tenants.id` is in the API and what the `Tenant` type declares —
 * string ids here would let type errors pass unnoticed in mocked runs.
 */

import type { HealthStatus, TenantKind } from "../types";
import type { components } from "../api/schema";

export interface MockTenant {
  id: number;
  name: string;
  display_name?: string;
  slug: string;
  kind: TenantKind;
  parent_tenant_id: number | null;
  depth: number;
  plan?: string;
  created_at: string;
  user_role?: string;
  // GET /tenants types each row as `{ [key: string]: unknown }` (mixed
  // detail/summary — see `get_list_user_tenants` in schema.d.ts), and
  // TypeScript does not treat a named interface as assignable to an
  // index-signature type unless it declares one too. This one is genuinely
  // that loose per the schema, not a hole punched in an otherwise-typed row.
  [key: string]: unknown;
}

/**
 * Widens a `MockTenant` fixture row to the generated `TenantDetail` schema.
 *
 * `MockTenant` predates the generated schema and is deliberately loose (most
 * fields optional, no `max_products`/`max_users`/`owner_id`/`status`) because
 * it also feeds `GET /tenants`, whose envelope types each row as
 * `{ [key: string]: unknown }` — see `schema.d.ts`'s `get_list_user_tenants`.
 * `POST /tenants/{id}/switch` is not that loose: it documents `tenant` as a
 * full `TenantDetail`, so a handler returning a bare `MockTenant` for it
 * would silently under-describe what the real endpoint sends. Defaults below
 * are mock-only filler for the fields `MockTenant` has no opinion on.
 */
export function toTenantDetail(
  tenant: MockTenant,
): components["schemas"]["TenantDetail"] {
  return {
    id: tenant.id,
    name: tenant.name,
    display_name: tenant.display_name ?? tenant.name,
    slug: tenant.slug,
    kind: tenant.kind,
    parent_tenant_id: tenant.parent_tenant_id,
    depth: tenant.depth,
    plan: tenant.plan ?? "free",
    status: "active",
    max_products: 100,
    max_users: 50,
    owner_id: tenant.parent_tenant_id ?? tenant.id,
    user_role: tenant.user_role ?? null,
  };
}

export interface MockProduct {
  id: number;
  product_type: string;
  display_name: string;
  health_status: HealthStatus;
}

export interface MockDashboardRollup {
  tenant_id: number;
  tenant_name: string;
  products: Array<{
    connection_id: number;
    product: string;
    status: HealthStatus;
  }>;
}

export const PROVIDER_ONE = 1;
export const PROVIDER_TWO = 2;

export const MOCK_TENANTS: MockTenant[] = [
  {
    id: PROVIDER_ONE,
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
    id: PROVIDER_TWO,
    name: "TechVision",
    display_name: "TechVision (Provider)",
    slug: "techvision",
    kind: "provider",
    parent_tenant_id: null,
    depth: 0,
    plan: "enterprise",
    created_at: "2025-02-01T00:00:00Z",
  },
  {
    id: 11,
    name: "Acme Production",
    display_name: "Acme Production",
    slug: "acme-prod",
    kind: "customer",
    parent_tenant_id: PROVIDER_ONE,
    depth: 1,
    plan: "professional",
    created_at: "2025-03-01T00:00:00Z",
  },
  {
    id: 12,
    name: "Acme Staging",
    display_name: "Acme Staging",
    slug: "acme-stage",
    kind: "customer",
    parent_tenant_id: PROVIDER_ONE,
    depth: 1,
    plan: "professional",
    created_at: "2025-03-05T00:00:00Z",
  },
  {
    id: 13,
    name: "TechVision Platform",
    display_name: "TechVision Platform",
    slug: "techvision-platform",
    kind: "customer",
    parent_tenant_id: PROVIDER_TWO,
    depth: 1,
    plan: "professional",
    created_at: "2025-04-01T00:00:00Z",
  },
  {
    id: 14,
    name: "TechVision Research",
    display_name: "TechVision Research",
    slug: "techvision-research",
    kind: "customer",
    parent_tenant_id: PROVIDER_TWO,
    depth: 1,
    plan: "free",
    created_at: "2025-04-10T00:00:00Z",
  },
];

export const MOCK_DASHBOARD_ROLLUP: MockDashboardRollup[] = [
  {
    tenant_id: 11,
    tenant_name: "Acme Production",
    products: [
      { connection_id: 201, product: "gough", status: "healthy" },
      { connection_id: 202, product: "nest", status: "healthy" },
      {
        connection_id: 203,
        product: "waddleai",
        status: "degraded",
      },
    ],
  },
  {
    tenant_id: 12,
    tenant_name: "Acme Staging",
    products: [
      { connection_id: 204, product: "gough", status: "healthy" },
      { connection_id: 205, product: "nest", status: "healthy" },
    ],
  },
  {
    tenant_id: 13,
    tenant_name: "TechVision Platform",
    products: [
      {
        connection_id: 206,
        product: "tobogganing",
        status: "healthy",
      },
      {
        connection_id: 207,
        product: "waddlebot",
        status: "healthy",
      },
    ],
  },
  {
    tenant_id: 14,
    tenant_name: "TechVision Research",
    products: [{ connection_id: 208, product: "elder", status: "unhealthy" }],
  },
];

/** Product connections returned per tenant scope. */
export const MOCK_PRODUCTS_BY_TENANT: Record<number, MockProduct[]> = {
  11: [
    {
      id: 101,
      product_type: "gough",
      display_name: "Gough (Prod)",
      health_status: "healthy",
    },
    {
      id: 102,
      product_type: "nest",
      display_name: "Nest (Prod)",
      health_status: "healthy",
    },
    {
      id: 103,
      product_type: "waddleai",
      display_name: "WaddleAI (Prod)",
      health_status: "degraded",
    },
  ],
  13: [
    {
      id: 104,
      product_type: "tobogganing",
      display_name: "Tobogganing (Platform)",
      health_status: "healthy",
    },
    {
      id: 105,
      product_type: "waddlebot",
      display_name: "WaddleBot (Platform)",
      health_status: "healthy",
    },
  ],
};

/** Simplified JWT payload used by the mock token generator. */
export interface MockTokenPayload {
  sub: string;
  tenant: number;
  home_tenant: number;
  roles: string[];
  scope: string[];
  iat: number;
  exp: number;
}

/**
 * Generates a mock JWT (base64 header.payload with a fake signature).
 * Test/dev fixture only — never a substitute for a real signed token.
 */
export function generateMockToken(payload: Partial<MockTokenPayload>): string {
  const defaults: MockTokenPayload = {
    sub: "user-1",
    tenant: PROVIDER_ONE,
    home_tenant: PROVIDER_ONE,
    roles: ["Admin"],
    scope: ["tenants:read", "products:read"],
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
  };

  const finalPayload = { ...defaults, ...payload };

  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(finalPayload));
  const signature = "fake_signature";

  return `${header}.${body}.${signature}`;
}

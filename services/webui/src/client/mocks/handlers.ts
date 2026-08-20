/**
 * MSW request handlers.
 *
 * Endpoint shapes follow task-2B-brief: tenants (with `include_children`),
 * the switch endpoint, the provider rollup, and the auth surface — plus the
 * `/api/ui/login` BFF adapter the shared-library login page posts to.
 *
 * Every response body that documents a real 200/201 schema in `schema.d.ts`
 * is bound to it with `satisfies MockResponse<path, method>` — the same
 * generic `api/portal.ts` uses for real requests. This is the drift guard
 * `dashboard/activity`'s history motivates: that endpoint's mock once carried
 * `action` while the server sent `action_type`, and nothing here caught it —
 * the mock agreed with the component, both disagreed with the server, and
 * every test stayed green while the field rendered `undefined` in production.
 * A `satisfies` mismatch now fails `npm run typecheck` (`tsc --noEmit`, part
 * of the pre-commit/CI gate). That alone is compile-time only, so
 * `mocks/__tests__/handlers.contract.test.ts` additionally asserts the
 * exported activity fixture's field set at runtime, under `npm test` — the
 * pair covers a `satisfies` weakened to `as` (still fails the runtime
 * assertion) and a typecheck step someone skipped locally (still fails CI).
 *
 * Endpoints still resolving to a `default`/unknown response in `schema.d.ts`
 * (most of them — see `api/portal.ts`'s own note on `@validate_response`
 * coverage) are bound with `MockResponse` rather than `ApiResponse` directly
 * — see that type's own doc comment below for why: `x satisfies unknown`
 * can never fail, so an endpoint bound directly against `ApiResponse` gives
 * no protection at all until the backend annotates it, and nothing marks
 * which ones are in that state.
 */

import { http, HttpResponse } from "msw";
import type { ApiPath, ApiResponse, HttpMethod } from "../api/portal";
import {
  MOCK_TENANTS,
  MOCK_DASHBOARD_ROLLUP,
  MOCK_PRODUCTS_BY_TENANT,
  PROVIDER_ONE,
  generateMockToken,
  toTenantDetail,
} from "./fixtures";

const API_BASE = "/api/v1";

/**
 * Endpoints bound below with NO real 200/201 schema yet — `ApiResponse<P,M>`
 * (`api/portal.ts`) resolves to `unknown` for these because the backend view
 * has no `@validate_response` annotation (see that file's own doc comment on
 * why the fallback is `unknown`, not `never`, for the real runtime client —
 * that reasoning is about `portal.get`/`.post` ergonomics and does not apply
 * here). `MockResponse` below treats this list as the ONLY endpoints allowed
 * to stay unconstrained; anything else must resolve to a real schema type or
 * fail to compile.
 *
 * Backend `@validate_response` coverage for these is tracked separately —
 * remove an entry once its endpoint gains a real schema, not before.
 */
type UnboundMockEndpoint =
  | "/api/v1/dashboard/overview:get"
  | "/api/v1/dashboard/health:get"
  | "/api/v1/auth/login:post"
  | "/api/v1/auth/me:get"
  | "/api/v1/auth/refresh:post"
  | "/api/v1/auth/logout:post"
  | "/api/v1/products:get"
  | "/api/v1/status:get"
  | "/api/v1/audit/logs:get"
  | "/api/v1/users:get";

/** True iff `T` is exactly `unknown` — not merely assignable to/from it. */
type IsExactlyUnknown<T> = [unknown] extends [T] ? true : false;

/**
 * Like `ApiResponse<P,M>`, except an endpoint NOT listed in
 * `UnboundMockEndpoint` must resolve to a real schema type, or this is
 * `never` — and `x satisfies never` fails to compile for any `x`, which
 * turns a newly-mocked, still-undocumented endpoint into a build error
 * instead of the silent pass `satisfies ApiResponse<...>` gave every one of
 * them before this type existed.
 */
type MockResponse<
  P extends ApiPath,
  M extends HttpMethod,
> = `${P}:${M}` extends UnboundMockEndpoint
  ? unknown
  : IsExactlyUnknown<ApiResponse<P, M>> extends true
    ? never
    : ApiResponse<P, M>;

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

/**
 * `GET /api/v1/dashboard/activity`'s fixture response, exported so
 * `mocks/__tests__/handlers.contract.test.ts` can assert on its field shape
 * directly rather than only on the type binding below — a `satisfies` that
 * were ever weakened to `as` would compile without protection, but this
 * assertion would not.
 */
export const MOCK_ACTIVITY_RESPONSE = {
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
} satisfies MockResponse<"/api/v1/dashboard/activity", "get">;

export const handlers = [
  /**
   * GET /api/v1/tenants?include_children=true
   * Flat roster; with include_children each provider also carries its
   * customers inline. Row shape is `{ [key: string]: unknown }` in the
   * generated schema (mixed detail/summary — see `get_list_user_tenants`),
   * so `satisfies` here protects the envelope (`count`, `tenants`), not the
   * per-row fields.
   */
  http.get(`${API_BASE}/tenants`, ({ request }) => {
    const includeChildren =
      new URL(request.url).searchParams.get("include_children") === "true";

    // `satisfies` applied per-branch, directly on each fresh literal — not
    // to `body` afterward. Excess-property checking only fires on a fresh
    // literal at the point it is checked; a variable reference (what this
    // was before) loses it, so an extra top-level field would compile.
    const body = includeChildren
      ? ({
          tenants: MOCK_TENANTS.map((t) => ({
            ...t,
            children: MOCK_TENANTS.filter((c) => c.parent_tenant_id === t.id),
          })),
          count: MOCK_TENANTS.length,
        } satisfies MockResponse<"/api/v1/tenants", "get">)
      : ({
          tenants: MOCK_TENANTS,
          count: MOCK_TENANTS.length,
        } satisfies MockResponse<"/api/v1/tenants", "get">);

    return HttpResponse.json(body);
  }),

  /**
   * POST /api/v1/tenants/:id/switch
   * Re-issues an access token whose claims name the new active tenant.
   *
   * The schema's `tenant` is a full `TenantDetail`, not the looser
   * `MockTenant` — `toTenantDetail` fills the fields `MockTenant` has no
   * opinion on. `refresh_token` is deliberately absent: it is not part of
   * this operation's documented response, and `tenantStore.ts` already falls
   * back to the token it already holds when this response omits one — the
   * mock previously always sent a fresh one, which meant that fallback path
   * was never exercised by anything using this handler.
   */
  http.post(`${API_BASE}/tenants/:id/switch`, ({ params }) => {
    const tenantId = Number(params.id);
    const tenant = MOCK_TENANTS.find((t) => t.id === tenantId);

    if (!tenant) {
      return HttpResponse.json({ error: "Tenant not found" }, { status: 404 });
    }

    const body = {
      access_token: tokenPair(tenantId).access_token,
      scope: ["tenants:read", "tenants:manage", "products:read"],
      tenant: toTenantDetail(tenant),
      tenant_role: "admin",
    } satisfies MockResponse<"/api/v1/tenants/{tenant_id}/switch", "post">;

    return HttpResponse.json(body);
  }),

  /**
   * GET /api/v1/tenants/:tenantId/dashboard/rollup
   * Per-customer × per-product status for the requesting provider org.
   *
   * Previously registered at the unscoped `GET /api/v1/dashboard/rollup?
   * tenant_id=` — a route the portal has never served (see
   * `api/resources/dashboard.ts` `rollup()`'s own note and
   * `api/portalPaths.ts`'s `tenantDashboardRollup`) — so nothing in the app
   * had called this handler since that fix landed. Rewiring it to the real
   * path is what let it be `satisfies`-bound at all: `ApiResponse` only
   * accepts a path the generated schema documents, and the old string
   * wasn't one. Binding it surfaced the same class of drift the activity
   * endpoint had: `MockDashboardRollup.products[].connection_id` was
   * `string` (e.g. "conn-gough-1") against the schema's `number` — fixed at
   * the fixture (see `MockDashboardRollup` in fixtures.ts).
   */
  http.get(`${API_BASE}/tenants/:tenantId/dashboard/rollup`, ({ params }) => {
    const tenantId = Number(params.tenantId);

    // Scoped to the caller's own customers — a provider must not see another
    // provider's subtree, which is what the delegated-admin check enforces.
    const customerIds = MOCK_TENANTS.filter(
      (t) => t.parent_tenant_id === tenantId,
    ).map((t) => t.id);
    const rollup = MOCK_DASHBOARD_ROLLUP.filter((row) =>
      customerIds.includes(row.tenant_id),
    );

    const body = {
      rollup,
      count: rollup.length,
    } satisfies MockResponse<
      "/api/v1/tenants/{tenant_id}/dashboard/rollup",
      "get"
    >;

    return HttpResponse.json(body);
  }),

  /** GET /api/v1/dashboard/overview */
  http.get(`${API_BASE}/dashboard/overview`, ({ request }) => {
    const tenantId = Number(
      new URL(request.url).searchParams.get("tenant_id") ?? NaN,
    );
    const products = MOCK_PRODUCTS_BY_TENANT[tenantId] ?? [];

    const body = {
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
    } satisfies MockResponse<"/api/v1/dashboard/overview", "get">;

    return HttpResponse.json(body);
  }),

  /**
   * GET /api/v1/dashboard/activity
   *
   * Field set mirrors the server's AuditRecord DTO exactly
   * (services/portal-api/app/audit_view.py). It previously carried `action`
   * while the server returned the raw row's `action_type`, so the mock
   * agreed with the component and neither agreed with the API — the badge
   * rendered undefined in the real app and every test passed. See
   * `MOCK_ACTIVITY_RESPONSE`'s doc comment above for how that is now guarded.
   */
  http.get(`${API_BASE}/dashboard/activity`, () =>
    HttpResponse.json(MOCK_ACTIVITY_RESPONSE),
  ),

  /** GET /api/v1/dashboard/health */
  http.get(`${API_BASE}/dashboard/health`, () => {
    const body = { status: "healthy" } satisfies MockResponse<
      "/api/v1/dashboard/health",
      "get"
    >;
    return HttpResponse.json(body);
  }),

  /**
   * POST /api/ui/login
   * BFF adapter endpoint consumed by the shared-library login page. Mirrors
   * the translation performed by src/server/authAdapter.ts. Not part of
   * `openapi/v1.yaml` (it is this app's own Express/BFF route, not a portal
   * API endpoint), so it is not `ApiResponse`-bound — there is no schema
   * entry for it to drift against.
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

  /**
   * GET /api/v1/auth/me — hydrates the auth store after login and on reload.
   *
   * `MOCK_USER satisfies MockResponse<...>` — NOT `{ ...MOCK_USER }
   * satisfies ...`. A spread was tried here and reverted: verified against
   * this repo's tsc (5.7.2), `{ ...src } satisfies Narrow` does not
   * re-trigger excess-property checking the way an explicit `{ a: 1, b: 2 }
   * satisfies Narrow` literal does — TypeScript only checks the properties
   * written directly in the literal, and a spread's contributed keys are
   * not "written" for that purpose. So the spread bought nothing here: a
   * bare `MOCK_USER` reference is exactly as (un)protected. This endpoint
   * is in `UnboundMockEndpoint` today, so it is moot either way — call out
   * for whoever removes it from that list later: getting real
   * excess-property protection means rewriting this as an explicit
   * literal against the real schema's fields, the way the `tenants` and
   * `tenants/{tenant_id}/switch` handlers above do, not adding a spread.
   */
  http.get(`${API_BASE}/auth/me`, () => {
    const body = MOCK_USER satisfies MockResponse<"/api/v1/auth/me", "get">;
    return HttpResponse.json(body);
  }),

  /** POST /api/v1/auth/login — direct API contract, no `success` envelope. */
  http.post(`${API_BASE}/auth/login`, async ({ request }) => {
    const requestBody = (await request.json().catch(() => ({}))) as {
      email?: string;
      password?: string;
    };

    if (!requestBody.email || !requestBody.password) {
      return HttpResponse.json(
        { error: "Email and password required" },
        { status: 400 },
      );
    }

    const body = {
      ...tokenPair(PROVIDER_ONE),
      token_type: "Bearer",
      expires_in: 3600,
      user: MOCK_USER,
    } satisfies MockResponse<"/api/v1/auth/login", "post">;

    return HttpResponse.json(body);
  }),

  /** POST /api/v1/auth/refresh */
  http.post(`${API_BASE}/auth/refresh`, async ({ request }) => {
    const requestBody = (await request.json().catch(() => ({}))) as {
      refresh_token?: string;
    };

    if (!requestBody.refresh_token) {
      return HttpResponse.json(
        { error: "Refresh token required" },
        { status: 400 },
      );
    }

    // tokenPair(...) result used directly, not spread — see the longer note
    // on GET /api/v1/auth/me above for why a spread would not add any
    // excess-property protection here either.
    const body = tokenPair(PROVIDER_ONE) satisfies MockResponse<
      "/api/v1/auth/refresh",
      "post"
    >;
    return HttpResponse.json(body);
  }),

  /** POST /api/v1/auth/logout */
  http.post(`${API_BASE}/auth/logout`, () => {
    const body = { success: true } satisfies MockResponse<
      "/api/v1/auth/logout",
      "post"
    >;
    return HttpResponse.json(body);
  }),

  /** GET /api/v1/products?tenant_id= */
  http.get(`${API_BASE}/products`, ({ request }) => {
    const tenantId = Number(
      new URL(request.url).searchParams.get("tenant_id") ?? NaN,
    );
    const products = MOCK_PRODUCTS_BY_TENANT[tenantId] ?? [];
    const body = {
      products,
      count: products.length,
    } satisfies MockResponse<"/api/v1/products", "get">;
    return HttpResponse.json(body);
  }),

  /**
   * GET /api/v1/status
   * Polled by the shared-library AppConsoleVersion banner in the footer; the
   * whole shell logs a failed request on every page without it.
   */
  http.get(`${API_BASE}/status`, () => {
    const body = {
      version: "1.0.0",
      build_epoch: 1754500000,
    } satisfies MockResponse<"/api/v1/status", "get">;
    return HttpResponse.json(body);
  }),

  /** GET /api/v1/audit/logs */
  http.get(`${API_BASE}/audit/logs`, () => {
    const body = { logs: [], total: 0 } satisfies MockResponse<
      "/api/v1/audit/logs",
      "get"
    >;
    return HttpResponse.json(body);
  }),

  /** GET /api/v1/users */
  http.get(`${API_BASE}/users`, () => {
    const body = {
      items: [MOCK_USER],
      total: 1,
      page: 1,
      per_page: 20,
      pages: 1,
    } satisfies MockResponse<"/api/v1/users", "get">;
    return HttpResponse.json(body);
  }),
];

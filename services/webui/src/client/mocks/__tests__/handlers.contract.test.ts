/**
 * @jest-environment node
 *
 * Drift guard for the MSW mock response shapes.
 *
 * Runs under the `node` environment, not the suite's default `jsdom`: `msw`
 * (imported by `handlers.ts`) reads the Fetch API's `Request`/`Response`
 * globals at module-load time, which real Node provides and jsdom does not.
 * Nothing else in this file needs a DOM.
 *
 * `handlers.ts` binds every response with a documented 200/201 schema to
 * `ApiResponse<path, method>` via `satisfies` — the same generic
 * `api/portal.ts` uses for real requests, derived from `schema.d.ts`, which
 * is generated from `openapi/v1.yaml` (`npm run generate:api`). A mock that
 * adds a field the API does not return, or omits one it does fails
 * `npm run typecheck` (`tsc --noEmit`).
 *
 * Typecheck alone was not enough to catch the regression this file exists
 * for: `dashboard/activity` carried `action` while the server sent
 * `action_type`, and it passed all 584 tests at the time regardless, because
 * nothing imported `handlers.ts` at all — a file nothing imports is a file
 * nothing type-checks, `satisfies` or not, and `npm test` does not itself run
 * `tsc`. The assertions below are the second, independent layer: a runtime
 * check, under `npm test`, of the exact field set `ActivityTab.tsx` reads.
 * A drift now has to survive both a full typecheck AND this assertion to
 * reach production unnoticed again.
 */
import { MOCK_ACTIVITY_RESPONSE } from "../handlers";

describe("MOCK_ACTIVITY_RESPONSE", () => {
  it("carries the exact AuditRecord field set the API documents", () => {
    const [entry] = MOCK_ACTIVITY_RESPONSE.activity;
    expect(entry).toBeDefined();
    expect(Object.keys(entry!).sort()).toEqual(
      [
        "action",
        "created_at",
        "id",
        "ip_address",
        "product_connection_id",
        "resource_id",
        "resource_type",
        "tenant_id",
        "user_id",
      ].sort(),
    );
  });

  it("uses `action`, not the server's old raw column name `action_type`", () => {
    // The specific historical bug: ActivityTab.tsx reads `log.action`. A mock
    // carrying `action_type` instead would satisfy nothing downstream, but
    // previously satisfied every test, because nothing here read the field
    // by name.
    const [entry] = MOCK_ACTIVITY_RESPONSE.activity;
    expect(entry).toHaveProperty("action", "tenant.switch");
    expect(entry).not.toHaveProperty("action_type");
  });

  it("reports a count consistent with the activity array it wraps", () => {
    expect(MOCK_ACTIVITY_RESPONSE.count).toBe(
      MOCK_ACTIVITY_RESPONSE.activity.length,
    );
  });
});

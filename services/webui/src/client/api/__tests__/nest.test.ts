/**
 * Tests for the Nest API bindings.
 *
 * Three properties matter here and none is visible by reading the calls:
 *
 * 1. **Every proxied path stays inside the allowlist and carries `{tenant}`
 *    literally.** The portal matches the rule before substituting the tenant's
 *    external id, so a path with the placeholder filled in — or with a
 *    trailing slash Nest does not register — is refused or 404s. The
 *    assertions name the exact path string for that reason.
 * 2. **Nest's collection envelope is unwrapped.** `{items: [...]}`, with an
 *    absent key meaning empty rather than broken.
 * 3. **A 503 from the cost routes is not an error.** It means
 *    `nest-cost-calculator` is not deployed, which is a deployment state; any
 *    other status is a real failure and must still throw.
 */

import api from "../../lib/api";
import { proxyRequestUrl } from "../portalPaths";
import { nestApi } from "../resources/nest";
import { nestResourcesApi } from "../resources/nestResources";

jest.mock("../../lib/api");

const mockApi = api as unknown as {
  get: jest.Mock;
  post: jest.Mock;
  delete: jest.Mock;
  request: jest.Mock;
};

/** The connection id every binding below is called with. */
const PRODUCT_ID = 7;

beforeEach(() => {
  jest.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: {} });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.request.mockResolvedValue({ data: {} });
});

/** The product-relative path the proxy binding forwarded. */
function forwardedPath(): string {
  const url = mockApi.request.mock.calls[0][0].url as string;
  const prefix = proxyRequestUrl(PRODUCT_ID, "");
  expect(url.startsWith(prefix)).toBe(true);
  return url.slice(prefix.length);
}

/** An axios-shaped rejection carrying an HTTP status. */
function httpError(status: number): Error & { response: { status: number } } {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status } });
}

describe("proxied reads", () => {
  it("addresses the data-resource collection with a literal {tenant}", async () => {
    // Filling the placeholder in the browser would send a PORTAL tenant id to
    // Nest and miss the allowlist besides. The browser never learns the
    // product-side id.
    mockApi.request.mockResolvedValue({ data: { items: [{ name: "db-1" }] } });

    const rows = await nestApi.listDatabases(PRODUCT_ID);

    expect(rows).toEqual([{ name: "db-1" }]);
    expect(forwardedPath()).toBe("api/v1/tenants/{tenant}/data-resources");
  });

  it("sends no trailing slash", async () => {
    // Nest registers every route without one; Werkzeug answers an extra slash
    // with a flat 404 and no redirect back, which reads as an empty table.
    await nestApi.listDatabases(PRODUCT_ID);

    expect(forwardedPath().endsWith("/")).toBe(false);
  });

  it("addresses one data-resource by name", async () => {
    await nestApi.getDatabase(PRODUCT_ID, "orders-primary");

    expect(forwardedPath()).toBe(
      "api/v1/tenants/{tenant}/data-resources/orders-primary",
    );
  });

  it("encodes a name rather than letting it compose a path", async () => {
    await nestApi.getDatabase(PRODUCT_ID, "../../auth/login");

    expect(forwardedPath()).toBe(
      "api/v1/tenants/{tenant}/data-resources/..%2F..%2Fauth%2Flogin",
    );
  });

  it("returns an empty list rather than throwing when items is absent", async () => {
    // Nest omits `items` for a genuinely empty collection; treating that as a
    // failure renders "no databases yet" as an outage.
    mockApi.request.mockResolvedValue({ data: { meta: { count: 0 } } });

    expect(await nestApi.listDatabases(PRODUCT_ID)).toEqual([]);
  });

  it("accepts a bare array as well as the envelope", async () => {
    mockApi.request.mockResolvedValue({ data: [{ name: "snap-1" }] });

    expect(await nestApi.listSnapshots(PRODUCT_ID)).toEqual([
      { name: "snap-1" },
    ]);
  });
});

describe("billing reads", () => {
  it("unwraps the cost envelope", async () => {
    mockApi.request.mockResolvedValue({
      data: { status: "ok", data: { records: [{ month: "2026-07" }] } },
    });

    const result = await nestApi.costReport(PRODUCT_ID);

    expect(result).toEqual({
      available: true,
      data: { records: [{ month: "2026-07" }] },
    });
    expect(forwardedPath()).toBe("api/v1/tenants/{tenant}/cost-report");
  });

  it("addresses the summary sub-collection, not an id", async () => {
    await nestApi.costSummary(PRODUCT_ID);

    expect(forwardedPath()).toBe("api/v1/tenants/{tenant}/cost-report/summary");
  });

  it("maps a 503 to unavailable rather than an error", async () => {
    // nest-cost-calculator absent — a deployment state, not a fault of this
    // request, and not a statement that the tenant was billed nothing.
    mockApi.request.mockRejectedValue(httpError(503));

    expect(await nestApi.costReport(PRODUCT_ID)).toEqual({
      available: false,
      data: null,
    });
  });

  it("reads Nest's own unavailable envelope as unavailable", async () => {
    mockApi.request.mockResolvedValue({
      data: { status: "unavailable", message: "Cost calculator unreachable" },
    });

    expect(await nestApi.costSummary(PRODUCT_ID)).toEqual({
      available: false,
      data: null,
    });
  });

  it.each([401, 403, 500])("still throws on %s", async (status) => {
    // Swallowing these would hide an auth or routing fault behind the same
    // "not deployed" notice the operator cannot act on.
    mockApi.request.mockRejectedValue(httpError(status));

    await expect(nestApi.costReport(PRODUCT_ID)).rejects.toThrow();
  });

  it("rethrows a network error, which carries no status at all", async () => {
    // `error.response` is undefined when the request never reached the portal.
    // Treating a missing status as "not 503" is what keeps an outage from
    // rendering as a deployment choice.
    mockApi.request.mockRejectedValue(new Error("Network Error"));

    await expect(nestApi.costSummary(PRODUCT_ID)).rejects.toThrow(
      "Network Error",
    );
  });

  it.each([
    ["a null body", null],
    ["a non-object body", "not json"],
  ])(
    "treats %s as unavailable rather than trusting it",
    async (_name, body) => {
      // A 200 with an unusable body is not a bill. Reading `data` off it would
      // produce `available: true` with nothing in it, which the screen would
      // render as a metered tenant that owes nothing.
      mockApi.request.mockResolvedValue({ data: body });

      expect(await nestApi.costReport(PRODUCT_ID)).toEqual({
        available: false,
        data: null,
      });
    },
  );

  it("reports an ok envelope with no data as available but empty", async () => {
    // Distinct from the case above: the calculator answered, it simply has no
    // records for this tenant yet.
    mockApi.request.mockResolvedValue({ data: { status: "ok" } });

    expect(await nestApi.costReport(PRODUCT_ID)).toEqual({
      available: true,
      data: null,
    });
  });
});

describe("collection unwrapping", () => {
  it("returns an empty list when items is present but not a list", async () => {
    // A shape this wrong is a product bug, but rendering an empty table is
    // still truthful about what arrived — and it keeps one malformed response
    // from throwing inside a screen that has no way to explain it.
    mockApi.request.mockResolvedValue({ data: { items: "nope" } });

    expect(await nestApi.listSnapshots(PRODUCT_ID)).toEqual([]);
  });

  it("returns null for a single resource that is not an object", async () => {
    mockApi.request.mockResolvedValue({ data: null });

    expect(await nestApi.getDatabase(PRODUCT_ID, "db-1")).toBeNull();
  });
});

describe("typed writes", () => {
  it("creates through the portal route, not the proxy", async () => {
    // Nest's allowlist is GET-only: a proxied create would be refused, and
    // even if admitted would return a raw 202 with no poll key.
    await nestResourcesApi.createDatabase(PRODUCT_ID, { name: "db-1" });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/7/resources/database",
      {
        name: "db-1",
      },
    );
    expect(mockApi.request).not.toHaveBeenCalled();
  });

  it("deletes by name through the portal route", async () => {
    await nestResourcesApi.deleteDatabase(PRODUCT_ID, "orders-primary");

    expect(mockApi.delete).toHaveBeenCalledWith(
      "/products/7/resources/database/orders-primary",
    );
  });

  it("encodes a name in a typed route too", async () => {
    await nestResourcesApi.deleteDatabase(PRODUCT_ID, "../../auth/login");

    expect(mockApi.delete).toHaveBeenCalledWith(
      "/products/7/resources/database/..%2F..%2Fauth%2Flogin",
    );
  });

  it("starts an action on the typed action route", async () => {
    await nestResourcesApi.performAction(
      PRODUCT_ID,
      "orders-primary",
      "snapshot",
    );

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/7/resources/database/orders-primary/actions/snapshot",
      {},
    );
  });

  it("polls an operation under Nest's single operation kind", async () => {
    // Every Nest action is polled at one route, so `kind` is a constant —
    // guessing an action-specific kind would 501.
    await nestResourcesApi.getOperation(PRODUCT_ID, "op-1");

    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/operation/op-1",
    );
  });
});

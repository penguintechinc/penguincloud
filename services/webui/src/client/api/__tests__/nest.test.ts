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
 * 2. **Each collection is unwrapped from ITS OWN key.** There is no shared
 *    envelope — only data-resources answers `items`; snapshots answer
 *    `snapshots`. Reading `items` for both and defaulting to `[]` is what made
 *    the Snapshots tab report "No snapshots have been taken from this
 *    resource" whatever Nest returned, so an absent key now throws.
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
    mockApi.request.mockResolvedValue({ data: { items: [] } });

    await nestApi.listDatabases(PRODUCT_ID);

    expect(forwardedPath().endsWith("/")).toBe(false);
  });

  it("reads snapshots from the `snapshots` key, not `items`", async () => {
    // `~/code/nest/apps/api/handlers/protection.py:26`. Only data-resources
    // answers `items`. The literal key is written out rather than imported
    // from the table so this cannot agree with a wrong table by construction.
    mockApi.request.mockResolvedValue({
      data: { snapshots: [{ name: "snap-1" }], meta: { count: 1 } },
    });

    expect(await nestApi.listSnapshots(PRODUCT_ID)).toEqual([
      { name: "snap-1" },
    ]);
    expect(forwardedPath()).toBe("api/v1/tenants/{tenant}/snapshots");
  });

  it("refuses to report an unrecognised shape as an empty collection", async () => {
    // The shipped behaviour returned [] here, and the Snapshots tab rendered
    // "No snapshots have been taken from this resource" — a false statement to
    // the operator with nothing anywhere reporting a problem.
    mockApi.request.mockResolvedValue({ data: { items: [{ name: "s" }] } });

    await expect(nestApi.listSnapshots(PRODUCT_ID)).rejects.toThrow(
      /no "snapshots" key/,
    );
  });

  it("still reports a genuinely empty collection as empty", async () => {
    // Strictness must not turn "none yet" into an error: Nest's list handlers
    // build their key unconditionally, so an empty collection arrives with the
    // key present and an empty list.
    mockApi.request.mockResolvedValue({
      data: { snapshots: [], meta: { count: 0 } },
    });

    expect(await nestApi.listSnapshots(PRODUCT_ID)).toEqual([]);
  });

  it("rejects a bare array, which is not a shape Nest answers", async () => {
    mockApi.request.mockResolvedValue({ data: [{ name: "snap-1" }] });

    await expect(nestApi.listSnapshots(PRODUCT_ID)).rejects.toThrow(
      /no collection envelope/,
    );
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
  it("throws when the key is present but not a list", async () => {
    // A shape this wrong is a product bug. Rendering an empty table would be
    // the screen asserting "there are none", which is not what arrived — the
    // caller's error boundary can say "could not read snapshots" instead.
    mockApi.request.mockResolvedValue({ data: { snapshots: "nope" } });

    await expect(nestApi.listSnapshots(PRODUCT_ID)).rejects.toThrow(
      /non-list under "snapshots"/,
    );
  });

  it("throws on a null body rather than reporting no rows", async () => {
    mockApi.request.mockResolvedValue({ data: null });

    await expect(nestApi.listDatabases(PRODUCT_ID)).rejects.toThrow(
      /no collection envelope/,
    );
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

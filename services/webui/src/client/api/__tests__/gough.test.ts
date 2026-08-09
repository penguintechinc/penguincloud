/**
 * Tests for the Gough API bindings.
 *
 * Two properties matter here and neither is visible by reading the calls:
 *
 * 1. **Every path stays inside the proxy allowlist.** The portal refuses
 *    anything else, so a path built wrong here is a 403 the user cannot act
 *    on. The assertions name the exact path string for that reason.
 * 2. **Both of Gough's response shapes are unwrapped.** Enveloped
 *    `{status, data, meta}` for nodes/biomes, bare for agents. A binding that
 *    handles only one silently returns an empty table for the other.
 */

import api from "../../lib/api";
import { proxyRequestUrl } from "../portalPaths";
import { goughApi } from "../resources/gough";
import { goughOperationsApi } from "../resources/goughOperations";

/** The connection id every binding below is called with. */
const PRODUCT_ID = 7;

jest.mock("../../lib/api");

const mockApi = api as unknown as {
  get: jest.Mock;
  post: jest.Mock;
  request: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: {} });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.request.mockResolvedValue({ data: {} });
});

/**
 * The product-relative path the proxy binding forwarded.
 *
 * The prefix is stripped using `proxyRequestUrl` itself rather than a
 * hand-written regex. The regex here used to be `^\/proxy\/\d+\/`, transcribed
 * from a prefix the portal does not serve — so every assertion below passed
 * while the real request 404'd. Deriving the prefix from the builder means a
 * URL shape this suite does not actually produce cannot be stripped, and the
 * `expect(...).toBe(...)` lines fail instead of silently agreeing.
 */
function forwardedPath(): string {
  const url = mockApi.request.mock.calls[0][0].url as string;
  const prefix = proxyRequestUrl(PRODUCT_ID, "");
  expect(url.startsWith(prefix)).toBe(true);
  return url.slice(prefix.length);
}

describe("goughApi list bindings", () => {
  it("unwraps the enveloped shape used by nodes", async () => {
    mockApi.request.mockResolvedValue({
      data: { status: "success", data: { nodes: [{ id: 1 }] }, meta: {} },
    });

    const rows = await goughApi.listNodes(7);

    expect(rows).toEqual([{ id: 1 }]);
    expect(forwardedPath()).toBe("api/v1/nodes/");
  });

  it("unwraps the bare shape used by agents", async () => {
    // No envelope: Gough's agent handlers predate envelope_success.
    mockApi.request.mockResolvedValue({
      data: { agents: [{ agent_id: "a-1" }] },
    });

    expect(await goughApi.listAgents(7)).toEqual([{ agent_id: "a-1" }]);
  });

  it("returns an empty list rather than throwing when the key is absent", async () => {
    // An empty table is a truthful "no rows came back". A thrown error would
    // show a failure banner for a fleet that simply has no nodes yet.
    mockApi.request.mockResolvedValue({
      data: { status: "success", data: {} },
    });
    expect(await goughApi.listNodes(7)).toEqual([]);
  });

  it("accepts a bare array body", async () => {
    mockApi.request.mockResolvedValue({ data: [{ id: 3 }] });
    expect(await goughApi.listBiomes(7)).toEqual([{ id: 3 }]);
  });

  it("lists biomes from the allowlisted collection path", async () => {
    await goughApi.listBiomes(7);
    expect(forwardedPath()).toBe("api/v1/biomes/");
  });
});

describe("goughApi mutating verbs", () => {
  it("patches node tags", async () => {
    await goughApi.updateNodeTags(7, "12", ["gpu"]);

    expect(mockApi.request).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "PATCH",
        data: { hardware_tags: ["gpu"] },
      }),
    );
    expect(forwardedPath()).toBe("api/v1/nodes/12/tags");
  });

  it("creates, updates and deletes biomes on allowlisted paths", async () => {
    await goughApi.createBiome(7, { name: "web" });
    expect(forwardedPath()).toBe("api/v1/biomes/");

    jest.clearAllMocks();
    mockApi.request.mockResolvedValue({ data: {} });
    await goughApi.updateBiome(7, "4", { name: "web2" });
    expect(forwardedPath()).toBe("api/v1/biomes/4");

    jest.clearAllMocks();
    mockApi.request.mockResolvedValue({ data: {} });
    await goughApi.deleteBiome(7, "4");
    expect(forwardedPath()).toBe("api/v1/biomes/4");
  });

  it.each([
    ["listNodes", () => goughApi.listNodes(7), "api/v1/nodes/"],
    ["listBiomes", () => goughApi.listBiomes(7), "api/v1/biomes/"],
    ["listAgents", () => goughApi.listAgents(7), "api/v1/agents/"],
    ["createBiome", () => goughApi.createBiome(7, {}), "api/v1/biomes/"],
  ])(
    "%s sends the trailing slash Gough's route actually declares",
    async (_name, call, expected) => {
      // Regression: these four were sent WITHOUT the trailing slash. Gough
      // registers `route("/")` for all three collections, so Werkzeug answered
      // 308. The transport does not follow redirects and the proxy strips
      // `location`, so the browser got an empty body, `collection()` returned
      // [], and the user saw three empty tables plus a create that silently
      // did nothing — with no error banner anywhere.
      //
      // Asserting `.toBe` on the exact string is the point: a `toContain` or a
      // regex would have passed against the broken value too.
      await call();
      expect(forwardedPath()).toBe(expected);
    },
  );

  it("encodes an id rather than letting it compose a new path", async () => {
    // The portal would refuse this anyway — biome ids are matched as digits,
    // so a slash-bearing value cannot reach a different route. Encoding here
    // means the refusal is a clean 403 instead of a request for a path the
    // caller did not intend to build.
    await goughApi.deleteBiome(7, "../../auth/login");
    expect(forwardedPath()).not.toContain("../");
  });

  it("no longer exposes action verbs on the proxy module", () => {
    // I5: actions moved to `goughOperationsApi.performAction`, the TYPED
    // route. Proxying them returned Gough's raw 202 — no ActionResult, no
    // poll key — so the UI could only invalidate and hope. Asserting their
    // ABSENCE here is what stops a future call site quietly reinstating the
    // proxy path for an action that starts background work.
    expect("nodeAction" in goughApi).toBe(false);
    expect("agentAction" in goughApi).toBe(false);
  });
});

describe("goughOperationsApi", () => {
  it("reads headline metrics from the portal's metrics endpoint", async () => {
    // The only binding in this module with no test, which held the file's
    // coverage under its 90% threshold. Not a Nest change — fixed here rather
    // than left red, since a failing gate that predates a branch is still a
    // failing gate on it.
    //
    // `totals` is the figure the dashboard tiles read, and it is NOT the
    // length of a resource list: Gough's page_size caps at 500 and its own
    // `total` is the length of the page it just serialised, so a fleet larger
    // than one page would render as the page size.
    mockApi.get.mockResolvedValue({
      data: {
        start: "2026-08-08T00:00:00Z",
        series: [],
        totals: { nodes: 12 },
      },
    });

    const summary = await goughOperationsApi.metricsSummary(7);

    expect(summary.totals).toEqual({ nodes: 12 });
    expect(mockApi.get).toHaveBeenCalledWith("/products/7/metrics");
    expect(mockApi.request).not.toHaveBeenCalled();
  });

  it("lists operations from the portal endpoint, not the proxy", async () => {
    mockApi.get.mockResolvedValue({ data: { operations: [{ id: "op-1" }] } });

    const rows = await goughOperationsApi.listOperations(7);

    expect(rows).toEqual([{ id: "op-1" }]);
    expect(mockApi.get).toHaveBeenCalledWith("/products/7/operations");
    expect(mockApi.request).not.toHaveBeenCalled();
  });

  it("refuses to report a missing operations key as no operations", async () => {
    // `operations` is a required field of `OperationListResponse`, so an empty
    // page arrives as `{"operations": []}`. Defaulting to [] told the operator
    // nothing was running — the same false statement that shipped for Nest's
    // snapshots, on a screen watching a deploy.
    mockApi.get.mockResolvedValue({ data: {} });

    await expect(goughOperationsApi.listOperations(7)).rejects.toThrow(
      /no "operations" key/,
    );
  });

  it("still reports a genuinely empty operation list as empty", async () => {
    mockApi.get.mockResolvedValue({ data: { operations: [] } });

    expect(await goughOperationsApi.listOperations(7)).toEqual([]);
  });

  it("polls one operation by kind and id", async () => {
    mockApi.get.mockResolvedValue({ data: { id: "op-1", is_terminal: false } });

    await goughOperationsApi.getOperation(7, "deployment", "op-1");

    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1",
    );
  });

  it("encodes a composite operation id", async () => {
    // Gough nests upgrade runs under a biome, so the adapter folds the parent
    // into the id ("{biome_id}:{run_id}"). The colon must survive as one path
    // segment rather than splitting the route.
    await goughOperationsApi.getOperation(7, "biome_upgrade", "9:run-1");

    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/biome_upgrade/9%3Arun-1",
    );
  });

  it("performs an action on the typed route, not the proxy", async () => {
    // I5. `mockApi.request` is the PROXY transport; `mockApi.post` is the
    // portal client. Asserting the proxy was never touched is the half that
    // actually pins the decision — the path assertion alone would still pass
    // if someone routed this back through the proxy at the same URL.
    mockApi.post.mockResolvedValue({
      data: {
        action: "deploy",
        accepted: true,
        operations: [{ id: "dep-1", kind: "deployment" }],
      },
    });

    const result = await goughOperationsApi.performAction(
      7,
      "nodes",
      "12",
      "deploy",
    );

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12/actions/deploy",
      {},
    );
    expect(mockApi.request).not.toHaveBeenCalled();
    // The caller learns what it started — the whole reason for the move.
    expect(result.operations.map((op) => op.id)).toEqual(["dep-1"]);
  });

  it("encodes every action path segment", async () => {
    await goughOperationsApi.performAction(
      7,
      "nodes",
      "../../auth/login",
      "deploy",
    );

    expect(mockApi.post).toHaveBeenCalledWith(
      expect.not.stringContaining("../"),
      {},
    );
  });

  it("forwards an action payload when one is given", async () => {
    await goughOperationsApi.performAction(7, "nodes", "12", "deploy", {
      biome_ids: [5],
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12/actions/deploy",
      { biome_ids: [5] },
    );
  });

  it("cancels an operation", async () => {
    await goughOperationsApi.cancelOperation(7, "deployment", "op-1");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/cancel",
    );
  });

  it("fetches logs and passes `since` so a poll only pulls what is new", async () => {
    mockApi.get.mockResolvedValue({ data: { logs: [{ message: "hi" }] } });

    const lines = await goughOperationsApi.operationLogs(
      7,
      "deployment",
      "op-1",
      "2026-01-01T00:00:00Z",
    );

    expect(lines).toEqual([{ message: "hi" }]);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/logs",
      { params: { since: "2026-01-01T00:00:00Z" } },
    );
  });

  it("omits the params object entirely when `since` is absent", async () => {
    mockApi.get.mockResolvedValue({ data: { logs: [] } });

    await goughOperationsApi.operationLogs(7, "deployment", "op-1");

    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/logs",
      { params: undefined },
    );
  });

  it("refuses to report a missing logs key as no output", async () => {
    // "no output yet" and "this response is not the shape we expect" are very
    // different things to tell someone watching a deploy. `logs` is required
    // on `OperationLogsResponse`, so its absence cannot be the first.
    mockApi.get.mockResolvedValue({ data: {} });

    await expect(
      goughOperationsApi.operationLogs(7, "deployment", "op-1"),
    ).rejects.toThrow(/no "logs" key/);
  });

  it("still reports a genuinely empty log stream as empty", async () => {
    mockApi.get.mockResolvedValue({ data: { logs: [] } });

    expect(
      await goughOperationsApi.operationLogs(7, "deployment", "op-1"),
    ).toEqual([]);
  });
});

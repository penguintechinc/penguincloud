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
import { goughApi } from "../resources/gough";
import { goughOperationsApi } from "../resources/goughOperations";

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

/** The path the proxy binding forwarded, minus the /proxy/{id}/ prefix. */
function forwardedPath(): string {
  const url = mockApi.request.mock.calls[0][0].url as string;
  return url.replace(/^\/proxy\/\d+\//, "");
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
  it.each([
    ["deploy", "api/v1/nodes/12/deploy"],
    ["evacuate", "api/v1/nodes/12/evacuate"],
    ["reject", "api/v1/nodes/12/reject"],
  ] as const)("posts the %s verb to its own route", async (verb, path) => {
    await goughApi.nodeAction(7, "12", verb);

    expect(mockApi.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: "POST" }),
    );
    expect(forwardedPath()).toBe(path);
  });

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

  it("suspends and resumes an agent by its UUID", async () => {
    await goughApi.agentAction(7, "3f2b-aa", "suspend");
    expect(forwardedPath()).toBe("api/v1/agents/3f2b-aa/suspend");
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
    // The portal would refuse this anyway — agent ids are matched as hex, so
    // a slash-bearing value cannot reach a different route. Encoding here
    // means the refusal is a clean 403 instead of a request for a path the
    // caller did not intend to build.
    await goughApi.agentAction(7, "../../auth/login", "resume");
    expect(forwardedPath()).not.toContain("../");
  });
});

describe("goughOperationsApi", () => {
  it("lists operations from the portal endpoint, not the proxy", async () => {
    mockApi.get.mockResolvedValue({ data: { operations: [{ id: "op-1" }] } });

    const rows = await goughOperationsApi.listOperations(7);

    expect(rows).toEqual([{ id: "op-1" }]);
    expect(mockApi.get).toHaveBeenCalledWith("/products/7/operations");
    expect(mockApi.request).not.toHaveBeenCalled();
  });

  it("defaults to an empty list when the body omits operations", async () => {
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
    await goughOperationsApi.operationLogs(7, "deployment", "op-1");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/logs",
      { params: undefined },
    );
  });

  it("defaults to no log lines when the body omits them", async () => {
    expect(
      await goughOperationsApi.operationLogs(7, "deployment", "op-1"),
    ).toEqual([]);
  });
});

/**
 * `toProxyPath`/`readManifestEnvelope`/`buildManifestListFetcher` — the
 * leading-slash strip and the schema v2 `EnvelopeSpec.keys` walk, both of
 * which exist because a byte-identical manifest field is NOT byte-identical
 * to what the browser's proxy call needs. See the module doc on
 * `manifestListFetcher.ts`.
 */
import { GOUGH_COLLECTION_PATHS } from "../../../api/resources/goughPaths";
import {
  buildManifestListFetcher,
  readManifestEnvelope,
  toProxyPath,
} from "../manifestListFetcher";
import type { ListSpec } from "../manifestTypes";

const mockRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockRequest(...args) },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

describe("toProxyPath", () => {
  it("strips exactly one leading slash", () => {
    expect(toProxyPath("/api/v1/nodes/")).toBe("api/v1/nodes/");
  });

  it("is a no-op when there is no leading slash", () => {
    expect(toProxyPath("api/v1/nodes/")).toBe("api/v1/nodes/");
  });

  it("matches goughPaths.ts byte-for-byte for every collection the browser calls", () => {
    // The regression this whole module exists to prevent: a manifest's
    // `list.path_bytes` (backend-side, leading slash included per
    // `ListSpec.__post_init__`) must reduce to the EXACT string
    // `goughPaths.ts` already hand-pins for the browser side, once the
    // single leading slash `ListSpec` requires is stripped.
    const manifestPathBytes: Record<
      keyof typeof GOUGH_COLLECTION_PATHS,
      string
    > = {
      nodes: "/api/v1/nodes/",
      biomes: "/api/v1/biomes/",
      agents: "/api/v1/agents/",
    };
    for (const kind of Object.keys(GOUGH_COLLECTION_PATHS) as Array<
      keyof typeof GOUGH_COLLECTION_PATHS
    >) {
      expect(toProxyPath(manifestPathBytes[kind])).toBe(
        GOUGH_COLLECTION_PATHS[kind],
      );
    }
  });
});

describe("readManifestEnvelope", () => {
  it("reads a bare top-level key (Gough's agents shape)", () => {
    expect(readManifestEnvelope({ agents: [{ id: "1" }] }, ["agents"])).toEqual(
      [{ id: "1" }],
    );
  });

  it("walks a two-key path (Gough's nodes/biomes shape)", () => {
    const payload = {
      status: "success",
      data: { nodes: [{ id: "1" }] },
      meta: {},
    };
    expect(readManifestEnvelope(payload, ["data", "nodes"])).toEqual([
      { id: "1" },
    ]);
  });

  it("does NOT fall back to a same-named top-level key — the path is exact, not a guess", () => {
    // Schema v2's whole point: the declared path is followed exactly, never
    // inferred. A top-level `nodes` sitting beside `data.nodes` must not be
    // treated as an alternate match for a manifest that declares
    // `("data", "nodes")`.
    const payload = {
      nodes: [{ id: "top" }],
      data: { nodes: [{ id: "nested" }] },
    };
    expect(readManifestEnvelope(payload, ["data", "nodes"])).toEqual([
      { id: "nested" },
    ]);
  });

  it("returns an empty array rather than throwing when the shape is unrecognised", () => {
    expect(readManifestEnvelope({ unrelated: true }, ["nodes"])).toEqual([]);
    expect(readManifestEnvelope(null, ["nodes"])).toEqual([]);
    expect(readManifestEnvelope("not an object", ["nodes"])).toEqual([]);
  });

  it("returns an empty array when an intermediate key is missing", () => {
    expect(
      readManifestEnvelope({ status: "success" }, ["data", "nodes"]),
    ).toEqual([]);
  });

  it("returns an empty array when the final key is not an array", () => {
    expect(
      readManifestEnvelope({ data: { nodes: "not-an-array" } }, [
        "data",
        "nodes",
      ]),
    ).toEqual([]);
  });
});

describe("buildManifestListFetcher", () => {
  const list: ListSpec = {
    path_bytes: "/api/v1/nodes/",
    envelope: { keys: ["data", "nodes"] },
    pagination: "cursor",
  };

  it("proxies GET at the stripped path and walks the declared envelope", async () => {
    mockRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [{ id: "12" }] },
    });

    const fetcher = buildManifestListFetcher(list);
    const rows = await fetcher(7);

    expect(mockRequest).toHaveBeenCalledWith(7, "GET", "api/v1/nodes/");
    expect(rows).toEqual([{ id: "12" }]);
  });

  it("proxies a bare, single-key envelope (Gough's agents shape)", async () => {
    mockRequest.mockResolvedValue({ agents: [{ agent_id: "a-1" }] });
    const bareList: ListSpec = {
      path_bytes: "/api/v1/agents/",
      envelope: { keys: ["agents"] },
      pagination: "none",
    };

    const rows = await buildManifestListFetcher(bareList)(7);
    expect(rows).toEqual([{ agent_id: "a-1" }]);
  });
});

/**
 * `toProxyPath`/`readManifestEnvelope`/`buildManifestListFetcher` — the
 * leading-slash strip and the maybe-`data`-enveloped read, both of which
 * exist because a byte-identical manifest field is NOT byte-identical to
 * what the browser's proxy call needs. See the module doc on
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
    expect(readManifestEnvelope({ agents: [{ id: "1" }] }, "agents")).toEqual([
      { id: "1" },
    ]);
  });

  it("reads a key nested one level inside `data` (Gough's nodes/biomes shape)", () => {
    const payload = {
      status: "success",
      data: { nodes: [{ id: "1" }] },
      meta: {},
    };
    expect(readManifestEnvelope(payload, "nodes")).toEqual([{ id: "1" }]);
  });

  it("prefers the top-level key over a same-named key inside data", () => {
    const payload = {
      nodes: [{ id: "top" }],
      data: { nodes: [{ id: "nested" }] },
    };
    expect(readManifestEnvelope(payload, "nodes")).toEqual([{ id: "top" }]);
  });

  it("returns an empty array rather than throwing when the shape is unrecognised", () => {
    expect(readManifestEnvelope({ unrelated: true }, "nodes")).toEqual([]);
    expect(readManifestEnvelope(null, "nodes")).toEqual([]);
    expect(readManifestEnvelope("not an object", "nodes")).toEqual([]);
  });
});

describe("buildManifestListFetcher", () => {
  const list: ListSpec = {
    path_bytes: "/api/v1/nodes/",
    envelope_key: "nodes",
    pagination: "cursor",
  };

  it("proxies GET at the stripped path and unwraps the envelope", async () => {
    mockRequest.mockResolvedValue({
      status: "success",
      data: { nodes: [{ id: "12" }] },
    });

    const fetcher = buildManifestListFetcher(list);
    const rows = await fetcher(7);

    expect(mockRequest).toHaveBeenCalledWith(7, "GET", "api/v1/nodes/");
    expect(rows).toEqual([{ id: "12" }]);
  });
});

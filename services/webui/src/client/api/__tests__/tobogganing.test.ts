/**
 * Tests for the Tobogganing API bindings.
 *
 * Three properties matter here and none is visible by reading the calls:
 *
 * 1. **Every path is exactly what the product registers.** Tobogganing mixes
 *    trailing-slash shapes within one API — `/api/v1/clusters/` is registered
 *    WITH one and `/api/v1/sdwan/clusters` WITHOUT, both `strict_slashes=True`
 *    — so the exact bytes are asserted rather than a prefix.
 * 2. **Each collection is unwrapped from ITS OWN key, and `items` is never
 *    one of them.** Nothing in Tobogganing answers `items`; assuming it would
 *    have emptied all five tables at once with nothing failing. An absent key
 *    throws rather than reporting "none".
 * 3. **The peer list is the SD-WAN one, not the flat one.** `/api/v1/sdwan/
 *    wireguard/peers` is user-reachable; `/api/v1/wireguard/peers` is the
 *    machine plane (`aud=="headend"`) and is one segment away from it.
 */

import api from "../../lib/api";
import { proxyRequestUrl } from "../portalPaths";
import { tobogganingApi } from "../resources/tobogganing";
import { blockPagePath } from "../resources/tobogganingPaths";

jest.mock("../../lib/api");

const mockApi = api as unknown as { request: jest.Mock };

/** The connection id every binding below is called with. */
const PRODUCT_ID = 7;

beforeEach(() => {
  jest.clearAllMocks();
  mockApi.request.mockResolvedValue({ data: {} });
});

/** The product-relative path and method the proxy binding forwarded. */
function forwarded(): { method: string; path: string; data: unknown } {
  const call = mockApi.request.mock.calls[0][0] as {
    method: string;
    url: string;
    data: unknown;
  };
  const prefix = proxyRequestUrl(PRODUCT_ID, "");
  expect(call.url.startsWith(prefix)).toBe(true);
  return {
    method: call.method,
    path: call.url.slice(prefix.length),
    data: call.data,
  };
}

describe("collection reads", () => {
  it.each([
    ["listClients", "api/v1/sdwan/clients", "clients"],
    ["listClusters", "api/v1/sdwan/clusters", "clusters"],
    ["listPeers", "api/v1/sdwan/wireguard/peers", "peers"],
    ["listBlockPages", "api/v1/sase/blockpages/pages", "pages"],
    ["listSwgPolicies", "api/v1/sase/swg/policy", "policies"],
  ] as const)(
    "%s reads %s and unwraps from %s",
    async (method, path, envelope) => {
      const row = { id: "x", node_id: "x" };
      mockApi.request.mockResolvedValue({ data: { [envelope]: [row] } });

      const rows = await tobogganingApi[method](PRODUCT_ID);

      expect(rows).toEqual([row]);
      expect(forwarded()).toMatchObject({ method: "GET", path });
    },
  );

  it("sends no path with a trailing slash", async () => {
    // Every one of these five routes is registered WITHOUT a trailing slash
    // and all are strict; a request carrying one earns a flat 404, which
    // surfaces to the operator as an empty table rather than an error.
    for (const read of [
      tobogganingApi.listClients,
      tobogganingApi.listClusters,
      tobogganingApi.listPeers,
      tobogganingApi.listBlockPages,
      tobogganingApi.listSwgPolicies,
    ]) {
      jest.clearAllMocks();
      mockApi.request.mockResolvedValue({
        data: {
          clients: [],
          clusters: [],
          peers: [],
          pages: [],
          policies: [],
        },
      });
      await read(PRODUCT_ID);
      expect(forwarded().path.endsWith("/")).toBe(false);
    }
  });

  it("reads the SD-WAN peer list, not the machine-plane one", async () => {
    // `/api/v1/wireguard/peers` is guarded by @require_machine_jwt, which
    // rejects any token whose `aud` is not "headend". A portal credential
    // carries aud=="tobogganing", so that route can never answer this screen —
    // an audience mismatch, not a scope one. The two paths differ by one
    // segment, which is exactly how the wrong one gets used.
    mockApi.request.mockResolvedValue({ data: { peers: [] } });

    await tobogganingApi.listPeers(PRODUCT_ID);

    expect(forwarded().path).toBe("api/v1/sdwan/wireguard/peers");
    expect(forwarded().path).not.toBe("api/v1/wireguard/peers");
  });

  it("throws rather than reporting an unrecognised shape as empty", async () => {
    // The 4N defect: `?? []` on a missing key is a false statement to the
    // operator, not a default. Every producer names its key unconditionally,
    // so an absent one means a shape this client does not understand.
    mockApi.request.mockResolvedValue({ data: { items: [{ id: "a" }] } });

    await expect(tobogganingApi.listClients(PRODUCT_ID)).rejects.toThrow(
      /no "clients" key/,
    );
  });

  it("throws on a non-list under a key that is present", async () => {
    mockApi.request.mockResolvedValue({ data: { peers: { node_id: "a" } } });

    await expect(tobogganingApi.listPeers(PRODUCT_ID)).rejects.toThrow(
      /non-list/,
    );
  });
});

describe("block page authoring", () => {
  it("creates a draft with the fields the product reads", async () => {
    await tobogganingApi.createBlockPage(PRODUCT_ID, {
      name: "Gambling",
      markdown: "# Blocked",
    });

    expect(forwarded()).toEqual({
      method: "POST",
      path: "api/v1/sase/blockpages/pages",
      data: { name: "Gambling", markdown: "# Blocked" },
    });
  });

  it("updates markdown only", async () => {
    // The product's update handler reads `markdown` and nothing else, so a
    // form offering a name edit would silently discard it.
    await tobogganingApi.updateBlockPage(PRODUCT_ID, "page-1", "# New");

    expect(forwarded()).toEqual({
      method: "PUT",
      path: "api/v1/sase/blockpages/pages/page-1",
      data: { markdown: "# New" },
    });
  });

  it("previews without publishing, defaulting the variables", async () => {
    await tobogganingApi.previewBlockPage(PRODUCT_ID, "page-1");

    expect(forwarded()).toEqual({
      method: "POST",
      path: "api/v1/sase/blockpages/pages/page-1/preview",
      data: { variables: {} },
    });
  });

  it("publishes a page", async () => {
    await tobogganingApi.publishBlockPage(PRODUCT_ID, "page-1");

    expect(forwarded()).toMatchObject({
      method: "POST",
      path: "api/v1/sase/blockpages/pages/page-1/publish",
    });
  });

  it("encodes an id rather than letting it compose a new path", () => {
    // The allowlist types the slot as a UUID, so the portal refuses a
    // path-shaped value too — this is the near end of the same rule.
    expect(blockPagePath("../../auth/login")).toBe(
      "api/v1/sase/blockpages/pages/..%2F..%2Fauth%2Flogin",
    );
  });
});

describe("SWG policy", () => {
  it("upserts a policy without naming a tenant", async () => {
    // The product derives the tenant from the JWT and rejects a body tenant
    // that disagrees, so sending one could only ever be wrong.
    await tobogganingApi.setSwgPolicy(PRODUCT_ID, {
      scope: "tenant",
      category: "gambling",
      action: "block",
    });

    const call = forwarded();
    expect(call).toMatchObject({
      method: "PUT",
      path: "api/v1/sase/swg/policy",
    });
    expect(call.data).not.toHaveProperty("tenant");
  });
});

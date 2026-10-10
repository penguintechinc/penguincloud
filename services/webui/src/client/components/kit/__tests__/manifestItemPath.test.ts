/**
 * `manifestItemPathBytes`/`toProxyItemPath` — the one place `{prefix}/{id}`
 * concatenation happens, so the trailing-slash defect class
 * `ItemPathSpec`'s doc names cannot creep back in via a second call site.
 */
import { manifestItemPathBytes, toProxyItemPath } from "../manifestItemPath";
import type { ItemPathSpec } from "../manifestTypes";

const NODES_ITEM_PATH: ItemPathSpec = {
  prefix: "/api/v1/nodes",
  sample_id: "1",
};

describe("manifestItemPathBytes", () => {
  it("appends the real id to the prefix with exactly one slash", () => {
    expect(manifestItemPathBytes(NODES_ITEM_PATH, "12")).toBe(
      "/api/v1/nodes/12",
    );
  });

  it("never re-uses sample_id — the real id always wins", () => {
    expect(manifestItemPathBytes(NODES_ITEM_PATH, "999")).not.toContain("/1");
    expect(manifestItemPathBytes(NODES_ITEM_PATH, "999")).toBe(
      "/api/v1/nodes/999",
    );
  });

  it("handles a prefix that coincides with its list path (biome_groups)", () => {
    const biomeGroups: ItemPathSpec = {
      prefix: "/api/v1/biomes/groups",
      sample_id: "1",
    };
    expect(manifestItemPathBytes(biomeGroups, "42")).toBe(
      "/api/v1/biomes/groups/42",
    );
  });
});

describe("toProxyItemPath", () => {
  it("strips the single leading slash, matching toProxyPath's own contract", () => {
    expect(toProxyItemPath(NODES_ITEM_PATH, "12")).toBe("api/v1/nodes/12");
  });

  it("matches manifestItemPathBytes with the slash removed, for a UUID id (agents)", () => {
    const agentsItemPath: ItemPathSpec = {
      prefix: "/api/v1/agents",
      sample_id: "11111111-1111-1111-1111-111111111111",
    };
    const id = "3f2b-aa";
    expect(toProxyItemPath(agentsItemPath, id)).toBe(
      manifestItemPathBytes(agentsItemPath, id).slice(1),
    );
  });
});

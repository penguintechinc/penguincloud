/**
 * The exact proxy paths for Gough's collection endpoints.
 *
 * Extracted into a constant of its own because the trailing slash is load
 * bearing and differs per collection, which is not something a reader infers
 * from the call site.
 *
 * Gough registers `nodes_bp.route("/")`, `biomes_bp.route("/")` and
 * `agents_bp.route("/")` WITH a trailing slash, but `biomes_bp.route("/groups")`
 * WITHOUT one, and never sets `strict_slashes`. Werkzeug's default handling is
 * asymmetric:
 *
 * - a request MISSING a registered trailing slash gets a **308 redirect**
 * - a request CARRYING a slash the route does not declare gets a flat **404**
 *
 * Neither is survivable here. The portal transport sets `followRedirects=false`
 * and the proxy strips `location`, so a 308 reaches the browser as an
 * empty-bodied response that `collection()` reads as zero rows — three empty
 * tables and a silent no-op create, with no error banner to act on.
 *
 * `tests/api/test_gough_webui_paths.py` asserts these strings equal
 * `_COLLECTION_ROUTES` in `app/adapters/gough/adapter.py`, so the two sides
 * cannot drift apart again without a red test.
 */

export const GOUGH_COLLECTION_PATHS = {
  nodes: "api/v1/nodes/",
  biomes: "api/v1/biomes/",
  biome_groups: "api/v1/biomes/groups",
  agents: "api/v1/agents/",
} as const;

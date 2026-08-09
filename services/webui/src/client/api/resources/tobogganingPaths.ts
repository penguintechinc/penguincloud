/**
 * The exact proxy paths for Tobogganing's collections, and the key each
 * collection's rows arrive under.
 *
 * Extracted for the reason `goughPaths.ts` and `nestPaths.ts` were: these
 * strings are a contract with the product, and a call site is not where a
 * reader can check them. `tests/api/test_tobogganing_webui_paths.py` compares
 * every entry below against the constants in
 * `app/adapters/tobogganing/routes.py` and `.../mapping.py`, which are in turn
 * graded against a live boot of Tobogganing — so neither side can drift alone
 * and neither is checked against a copy of itself.
 *
 * Nothing in Tobogganing answers `items`
 * ======================================
 * Every list route names its rows differently and **no route anywhere in the
 * product uses `items`**. Phase 4N shipped the opposite assumption against
 * Nest, where four kinds were decoded as `items`, three of them rendered as
 * permanently empty, and the UI stated it to the operator as fact ("No
 * snapshots have been taken"). Had these screens assumed `items`, **every**
 * Tobogganing table would have been empty with nothing failing anywhere.
 *
 * The keys below are therefore per-route, and `envelopeList` throws on an
 * absent key rather than returning `[]` — the only reading an operator can give
 * an empty list is "there are none".
 *
 * Trailing slashes are asymmetric WITHIN this product
 * ===================================================
 * Every Tobogganing rule is `strict_slashes=True`, and it registers both
 * shapes for two paths that read alike:
 *
 * - `GET /api/v1/clusters/`      — registered WITH the slash. A request
 *   without it earns a 308 the portal transport does not follow.
 * - `GET /api/v1/sdwan/clusters` — registered WITHOUT. A request with one
 *   earns a flat 404 with no redirect back.
 *
 * Both surface to the operator as an empty table rather than an error, so
 * appending a slash uniformly and stripping it uniformly are both defects, in
 * opposite directions. The screens here address the SD-WAN cluster list (the
 * tenant-scoped one), so no path below carries a trailing slash — and the guard
 * asserts that rather than leaving it to whoever next tidies the file.
 *
 * No `{tenant}` placeholder
 * =========================
 * Unlike Nest, Tobogganing takes no tenant in any path: every user-plane
 * handler reads `claims["tenant"]` from the JWT the portal presents. There is
 * consequently nothing here for the portal to substitute, and nothing the
 * browser could get wrong by choosing a tenant id — which is the safer shape.
 */

/** Collections the Tobogganing screens fetch through the proxy. */
export const TOBOGGANING_COLLECTION_PATHS = {
  clients: "api/v1/sdwan/clients",
  clusters: "api/v1/sdwan/clusters",
  peers: "api/v1/sdwan/wireguard/peers",
  blockPages: "api/v1/sase/blockpages/pages",
  swgPolicies: "api/v1/sase/swg/policy",
} as const;

/**
 * The key each collection's rows arrive under. Not a shared envelope — see the
 * module docstring. Bound to `COLLECTION_ENVELOPE_KEYS` in
 * `app/adapters/tobogganing/mapping.py` by the Python guard.
 */
export const TOBOGGANING_COLLECTION_ENVELOPE_KEYS = {
  clients: "clients",
  clusters: "clusters",
  peers: "peers",
  blockPages: "pages",
  swgPolicies: "policies",
} as const;

/** Literal sub-collections beneath a block page id. */
export const BLOCK_PAGE_SEGMENT_PREVIEW = "preview";
export const BLOCK_PAGE_SEGMENT_PUBLISH = "publish";

/**
 * Build a block-page item path.
 *
 * Mirrors `blockpage_path()` in the adapter, including its "no trailing slash"
 * rule; the guard asserts the built shapes against the proxy allowlist, so a
 * divergence fails there rather than as a 404 an operator reads as "no pages".
 *
 * `pageId` is encoded because it reaches the path from a product payload. The
 * allowlist types the slot as a UUID, so a path-shaped value is refused by the
 * portal too — encoding here is the near end of the same rule, not a substitute
 * for it.
 */
export function blockPagePath(pageId: string, segment?: string): string {
  const base = `${TOBOGGANING_COLLECTION_PATHS.blockPages}/${encodeURIComponent(pageId)}`;
  return segment ? `${base}/${segment}` : base;
}

/**
 * Tobogganing reads and writes, all through the portal PROXY.
 *
 * Unlike Nest, the writes are here rather than on typed portal routes. That is
 * not a shortcut — it follows the rule in `app/adapters/base.py`: a mutation
 * needs a typed adapter method when the caller needs something the product's
 * own response body does not already say. Every Nest write answers `202` with
 * an `operationId` to poll, so all of them qualified. **Tobogganing's
 * user-plane surface has no asynchronous operations at all** — no handler under
 * `modules/sase`, `modules/sdwan/api` or `api/` returns 202; every mutation
 * answers 200/201 with the resulting object. There is no `Operation` to poll
 * and no `ActionResult` to build, so the proxy's byte-pipe behaviour loses
 * nothing, and the SASE authoring verbs are allowlisted under the `manage`
 * scope in `app/adapters/tobogganing/routes.py`.
 *
 * Every path comes from `tobogganingPaths.ts`, which the Python guard pins
 * against the adapter's own constants. No URL is spelled here.
 */

import { envelopeList, envelopeString } from "../envelope";
import { proxyApi } from "./products";
import {
  BLOCK_PAGE_SEGMENT_PREVIEW,
  BLOCK_PAGE_SEGMENT_PUBLISH,
  blockPagePath,
  TOBOGGANING_COLLECTION_ENVELOPE_KEYS,
  TOBOGGANING_COLLECTION_PATHS,
  TOBOGGANING_PREVIEW_HTML_KEY,
} from "./tobogganingPaths";
import type {
  TobogganingBlockPage,
  TobogganingClient,
  TobogganingCluster,
  TobogganingPeer,
  TobogganingSwgPolicy,
} from "../../pages/products/tobogganing/types";

/** Read one collection and unwrap it under the key that route publishes. */
async function list<T>(
  productId: number,
  collection: keyof typeof TOBOGGANING_COLLECTION_PATHS,
): Promise<T[]> {
  return envelopeList<T>(
    await proxyApi.request(
      productId,
      "GET",
      TOBOGGANING_COLLECTION_PATHS[collection],
    ),
    TOBOGGANING_COLLECTION_ENVELOPE_KEYS[collection],
  );
}

export const tobogganingApi = {
  listClients: (productId: number): Promise<TobogganingClient[]> =>
    list<TobogganingClient>(productId, "clients"),

  listClusters: (productId: number): Promise<TobogganingCluster[]> =>
    list<TobogganingCluster>(productId, "clusters"),

  listPeers: (productId: number): Promise<TobogganingPeer[]> =>
    list<TobogganingPeer>(productId, "peers"),

  listBlockPages: (productId: number): Promise<TobogganingBlockPage[]> =>
    list<TobogganingBlockPage>(productId, "blockPages"),

  listSwgPolicies: (productId: number): Promise<TobogganingSwgPolicy[]> =>
    list<TobogganingSwgPolicy>(productId, "swgPolicies"),

  /** Create a DRAFT block page. Publishing is a separate, guarded verb. */
  createBlockPage: async (
    productId: number,
    payload: { name: string; markdown: string },
  ): Promise<TobogganingBlockPage> =>
    (await proxyApi.request(
      productId,
      "POST",
      TOBOGGANING_COLLECTION_PATHS.blockPages,
      payload,
    )) as TobogganingBlockPage,

  /**
   * Replace a block page's markdown.
   *
   * The product takes `markdown` only — `name` is not updatable through this
   * route, so a form offering it would silently discard the edit.
   */
  updateBlockPage: async (
    productId: number,
    pageId: string,
    markdown: string,
  ): Promise<TobogganingBlockPage> =>
    (await proxyApi.request(productId, "PUT", blockPagePath(pageId), {
      markdown,
    })) as TobogganingBlockPage,

  /**
   * Render a page without publishing it, returning the HTML itself.
   *
   * A POST that mutates nothing, which is the product's shape rather than a
   * choice here: it takes a `variables` body, so it cannot be a GET.
   *
   * The `html` key is unwrapped HERE rather than by the caller. Returning the
   * envelope let `useBlockPagePreview` write `preview.html ?? ""`, which is
   * the "report nothing as none" class one layer over: a renamed key would
   * render a blank white iframe with no error anywhere. Decoding at the
   * boundary means no call site is in a position to add that fallback back.
   */
  previewBlockPage: async (
    productId: number,
    pageId: string,
    variables?: Record<string, string>,
  ): Promise<string> =>
    envelopeString(
      await proxyApi.request(
        productId,
        "POST",
        blockPagePath(pageId, BLOCK_PAGE_SEGMENT_PREVIEW),
        { variables: variables ?? {} },
      ),
      TOBOGGANING_PREVIEW_HTML_KEY,
    ),

  /** Publish a draft. This is what makes the page live for blocked users. */
  publishBlockPage: async (
    productId: number,
    pageId: string,
  ): Promise<TobogganingBlockPage> =>
    (await proxyApi.request(
      productId,
      "POST",
      blockPagePath(pageId, BLOCK_PAGE_SEGMENT_PUBLISH),
    )) as TobogganingBlockPage,

  /**
   * Set one SWG category policy.
   *
   * An upsert keyed on (scope, scope_id, category), so saving a category that
   * already has a policy replaces its action rather than adding a second row.
   * The tenant is NOT sent: the product derives it from the JWT and rejects a
   * body tenant that disagrees, so supplying one could only ever be wrong.
   */
  setSwgPolicy: async (
    productId: number,
    payload: {
      scope: string;
      scope_id?: string | null;
      category: string;
      action: string;
    },
  ): Promise<unknown> =>
    proxyApi.request(
      productId,
      "PUT",
      TOBOGGANING_COLLECTION_PATHS.swgPolicies,
      payload,
    ),
};

/**
 * Block-page writes and the preview fetch.
 *
 * Every one of these is SYNCHRONOUS at the product — 200/201 with the
 * resulting object, no `operationId` — so each mutation's `onSuccess`
 * invalidating the list is the whole refresh story. There is nothing to poll,
 * which is why Tobogganing has no operations panel while Nest and Gough do.
 */

import { useState } from "react";
import { tobogganingApi } from "../../../api/resources/tobogganing";
import { TOBOGGANING_KINDS, useTobogganingMutation } from "./useTobogganing";

const KIND = TOBOGGANING_KINDS.blockPages;

export const useCreateBlockPage = () =>
  useTobogganingMutation<{ name: string; markdown: string }, unknown>(
    KIND,
    (productId, vars) => tobogganingApi.createBlockPage(productId, vars),
  );

export const useUpdateBlockPage = () =>
  useTobogganingMutation<{ pageId: string; markdown: string }, unknown>(
    KIND,
    (productId, vars) =>
      tobogganingApi.updateBlockPage(productId, vars.pageId, vars.markdown),
  );

export const usePublishBlockPage = () =>
  useTobogganingMutation<{ pageId: string }, unknown>(KIND, (productId, vars) =>
    tobogganingApi.publishBlockPage(productId, vars.pageId),
  );

/**
 * Render a preview on demand.
 *
 * Deliberately NOT a `useQuery`. Preview is a POST that renders the page with
 * sample variables; caching it under a query key would make an operator's
 * second look at an edited page return the pre-edit render, and prefetching it
 * would send a request per row on mount for content nobody asked to see.
 *
 * `html` is reset to null on each new request so a stale render is never shown
 * beside a different page's title.
 */
export function useBlockPagePreview(productId: number | undefined) {
  const [html, setHtml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const run = async (pageId: string): Promise<void> => {
    if (productId === undefined) return;
    setHtml(null);
    setError(null);
    setIsLoading(true);
    try {
      // `previewBlockPage` already unwrapped and validated the `html` key, so
      // there is no envelope to read and nothing here to default. A `?? ""`
      // at this line was the one product key this phase read at a call site,
      // and it rendered a blank iframe for a renamed key.
      setHtml(await tobogganingApi.previewBlockPage(productId, pageId));
    } catch (caught) {
      setError(caught as Error);
    } finally {
      setIsLoading(false);
    }
  };

  const reset = (): void => {
    setHtml(null);
    setError(null);
    setIsLoading(false);
  };

  return { html, isLoading, error, run, reset };
}

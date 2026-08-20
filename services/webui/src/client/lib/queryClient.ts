/**
 * The single `QueryClient` factory for the app.
 *
 * This is the shared mutation path: `MutationCache.onError` runs for every
 * `useMutation` in the app — Gough, Nest, Tobogganing, and anything added
 * later — regardless of whether that mutation's own hook defines an
 * `onError`. TanStack Query calls the cache-level handler in addition to,
 * never instead of, a mutation's own callbacks (`query-core`'s
 * `Mutation#execute`), so this is one place to guarantee a rejected save is
 * never silent, instead of one guarantee repeated per product hook — three
 * copies is how the previous state (no product had it) happened.
 *
 * A factory, not a module-level singleton, so tests can build an independent
 * client wired to the same `onError` behaviour they are trying to prove,
 * rather than reimplementing it inline per test file.
 */
import { MutationCache, QueryClient } from "@tanstack/react-query";
import { describeMutationError } from "./mutationError";
import { useMutationErrorStore } from "../stores/mutationErrorStore";

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    mutationCache: new MutationCache({
      onError: (error) => {
        useMutationErrorStore.getState().report(describeMutationError(error));
      },
      // Coarse by design: a successful mutation clears the WHOLE queue, not
      // just an entry that shares its identity. Product mutation hooks
      // (useGoughMutation, useTobogganingMutation, useDatabaseMutations)
      // don't thread a `mutationKey`, so there is nothing reliable to
      // correlate "this success" back to "that specific earlier failure"
      // with. This is still strictly better than the prior behaviour
      // (nothing ever cleared, so a failure stayed pinned for the rest of
      // the session even after the same save succeeded on retry) — the
      // cross-screen edge case this doesn't handle precisely is bounded
      // separately by clearing on every route change, see
      // hooks/useClearMutationErrorsOnNavigate.ts.
      onSuccess: () => {
        useMutationErrorStore.getState().clearAll();
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 5, // 5 minutes
        gcTime: 1000 * 60 * 10, // 10 minutes (formerly cacheTime)
        retry: false,
      },
    },
  });
}

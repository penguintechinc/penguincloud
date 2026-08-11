/**
 * The one fetch of `GET /api/v1/features`, mirrored into the gate store.
 *
 * Mounted once near the app root. Every other consumer reads the store
 * (`lib/featureGates.ts`) rather than issuing its own query, so a flag answer
 * cannot differ between two screens rendered at the same moment.
 *
 * A failed fetch deliberately leaves the store at its fail-closed default
 * (everything off, community tier) AND surfaces the error to the caller. Both
 * halves matter: silently defaulting would render "this product is behind a
 * feature flag that is currently off" for a response the client could not
 * read, which is a sentence an operator will believe.
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { featuresApi } from "../api/resources/features";
import type { FeaturesPayload } from "../api/resources/features";
import { queryKeys } from "../api/keys";
import { useFeatureGateStore } from "../lib/featureGates";

/** How long a flag answer is reused before refetching. */
const FEATURES_STALE_TIME_MS = 60_000;

/**
 * Fetch feature state and publish it to the gate store.
 *
 * @param enabled - false while unauthenticated; the endpoint requires a token.
 */
export function useFeatures(enabled = true) {
  const setFeatures = useFeatureGateStore((state) => state.setFeatures);

  const query = useQuery({
    queryKey: queryKeys.features(),
    queryFn: async (): Promise<FeaturesPayload> => featuresApi.get(),
    enabled,
    staleTime: FEATURES_STALE_TIME_MS,
    // Refetched on focus so a flag flipped by an operator reaches an open
    // tab without a reload. `dev_mode` in particular is re-evaluated
    // server-side per request, so a deployment that grows past one user
    // stops reporting it here too.
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (query.data) {
      setFeatures(query.data);
      return;
    }
    if (query.isError) {
      // Explicitly publish "nothing known" rather than leaving a previous
      // tenant's or session's answer in place.
      setFeatures(null);
    }
  }, [query.data, query.isError, setFeatures]);

  return query;
}

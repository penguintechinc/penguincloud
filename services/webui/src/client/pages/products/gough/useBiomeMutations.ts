/**
 * Create/update/delete mutations for biomes.
 *
 * Split from BiomesPage so the page stays under the 5000-character limit and
 * the create-vs-update branch is testable without rendering a table, a
 * drawer and two modals to reach it.
 */

import { goughApi } from "../../../api/resources/gough";
import { useGoughMutation } from "./useGough";

/**
 * One mutation for both create and update.
 *
 * `id === null` means create. Keeping them together rather than as two hooks
 * is what lets the form modal be a single component whose submit handler does
 * not branch on which mode opened it — the page already tracks that in
 * `editing`, and duplicating the decision is how the two drift.
 */
export function useSaveBiome() {
  return useGoughMutation<{
    id: string | null;
    payload: Record<string, unknown>;
  }>("biomes", (productId, vars) =>
    vars.id === null
      ? goughApi.createBiome(productId, vars.payload)
      : goughApi.updateBiome(productId, vars.id, vars.payload),
  );
}

/** Deletes a biome definition. Requires `products:gough:manage`. */
export function useDeleteBiome() {
  return useGoughMutation<{ id: string }>("biomes", (productId, vars) =>
    goughApi.deleteBiome(productId, vars.id),
  );
}

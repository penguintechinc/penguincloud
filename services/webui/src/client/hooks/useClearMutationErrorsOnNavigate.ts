/**
 * Clears every queued mutation error whenever the route changes.
 *
 * `mutationErrorStore` is deliberately session-wide — it exists specifically
 * to survive the form/dialog that raised the error closing (see
 * `stores/mutationErrorStore.ts`). "Survives navigating away to an unrelated
 * screen" was never the intent: a failure on a Gough page has no business
 * staying pinned while the operator goes and works in Nest. Mounted once in
 * `Layout`, which wraps every authenticated route, so this fires on every
 * route change regardless of which screen raised the error being cleared.
 */
import { useEffect } from "react";
import { useLocation } from "react-router";
import { useMutationErrorStore } from "../stores/mutationErrorStore";

export function useClearMutationErrorsOnNavigate(): void {
  const { pathname } = useLocation();
  const clearAll = useMutationErrorStore((state) => state.clearAll);

  useEffect(() => {
    clearAll();
    // `clearAll` is a stable Zustand action reference (identical across
    // renders), so including it here never causes an extra run — only a
    // `pathname` change does.
  }, [pathname, clearAll]);
}

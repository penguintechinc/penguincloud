/**
 * Client-only UI state for surfaced mutation failures.
 *
 * Not server state — TanStack Query already owns each mutation's own
 * transient `error`/`isError`, but that state disappears the moment the
 * component that called `useMutation` unmounts (e.g. a form closing). This
 * store is the part that survives: `lib/queryClient.ts` wires a global
 * `MutationCache.onError`/`onSuccess` to `report()`/`clearAll()` here for
 * every mutation in the app, `hooks/useClearMutationErrorsOnNavigate.ts`
 * clears on every route change, and `components/kit/MutationErrorBanner.tsx`
 * renders whatever is left queued from a mount point that outlives any one
 * form or page.
 */
import { create } from "zustand";

export interface MutationErrorEntry {
  id: number;
  message: string;
}

interface MutationErrorState {
  errors: MutationErrorEntry[];
  report: (message: string) => void;
  dismiss: (id: number) => void;
  clearAll: () => void;
}

let nextId = 0;

/**
 * Hard cap on queued entries. Nothing before this bounded the queue, so a
 * burst of failures (three quick Save clicks, or several independent
 * screens failing before anyone clears the last one) grew the banner stack
 * without limit — a `flex-col` of unbounded height that can overflow the
 * viewport, per M1/I3 in the mutation-error-surfacing review.
 */
const MAX_QUEUED_ERRORS = 5;

export const useMutationErrorStore = create<MutationErrorState>((set, get) => ({
  errors: [],
  report: (message) => {
    // Dedupe by message: bump the existing entry to the front (so it
    // reads as "still happening", not lost among newer ones) instead of
    // stacking an identical banner every time the same failure repeats —
    // three Save clicks on the same broken form produced three identical
    // banners before this.
    const existing = get().errors.find((e) => e.message === message);
    if (existing) {
      console.log(
        "[MutationErrorStore] Report (duplicate, bumped) { id:",
        existing.id,
        "}",
      );
      set((state) => ({
        errors: [...state.errors.filter((e) => e.id !== existing.id), existing],
      }));
      return;
    }

    const entry = { id: nextId++, message };
    console.log("[MutationErrorStore] Report { id:", entry.id, "}");
    set((state) => ({
      errors: [...state.errors, entry].slice(-MAX_QUEUED_ERRORS),
    }));
  },
  dismiss: (id) => {
    set((state) => ({ errors: state.errors.filter((e) => e.id !== id) }));
  },
  clearAll: () => {
    set({ errors: [] });
  },
}));

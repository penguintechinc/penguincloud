/**
 * Client-only UI state for surfaced mutation failures.
 *
 * Not server state — TanStack Query already owns each mutation's own
 * transient `error`/`isError`, but that state disappears the moment the
 * component that called `useMutation` unmounts (e.g. a form closing). This
 * store is the part that survives: `lib/queryClient.ts` wires a global
 * `MutationCache.onError` to `report()` here for every mutation in the app,
 * and `components/kit/MutationErrorBanner.tsx` renders whatever is queued
 * from a mount point that outlives any one form or page.
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
}

let nextId = 0;

export const useMutationErrorStore = create<MutationErrorState>((set) => ({
  errors: [],
  report: (message) => {
    const entry = { id: nextId++, message };
    console.log("[MutationErrorStore] Report { id:", entry.id, "}");
    set((state) => ({ errors: [...state.errors, entry] }));
  },
  dismiss: (id) => {
    set((state) => ({ errors: state.errors.filter((e) => e.id !== id) }));
  },
}));

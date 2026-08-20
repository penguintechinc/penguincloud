import { AlertCircle, X } from "lucide-react";
import { useMutationErrorStore } from "../../stores/mutationErrorStore";

/**
 * Renders every mutation failure `lib/queryClient.ts`'s global
 * `MutationCache.onError` has queued in `mutationErrorStore`.
 *
 * Mounted once in `Layout`, so it outlives whatever form or dialog triggered
 * the mutation — a form closing (or being force-closed, as `SwgPolicyPage`
 * used to do before the save it started was known to have failed) no longer
 * takes the error with it. `role="alert"` + `aria-live="assertive"` announce
 * each entry to assistive tech as it appears, matching `DataTableError`'s
 * palette so a save failure and a load failure read as the same kind of
 * event. Dismissible (unlike `DevModeBanner`, which is deliberately not):
 * this reports one past event rather than describing the deployment's
 * current state, so there is nothing wrong with it going away once read.
 */
export default function MutationErrorBanner() {
  const errors = useMutationErrorStore((state) => state.errors);
  const dismiss = useMutationErrorStore((state) => state.dismiss);

  if (errors.length === 0) return null;

  return (
    <div
      data-testid="mutation-error-banner"
      className="fixed top-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      {errors.map((entry) => (
        <div
          key={entry.id}
          role="alert"
          aria-live="assertive"
          data-testid={`mutation-error-${entry.id}`}
          className="w-full bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded shadow-lg"
        >
          <div className="flex items-start gap-3">
            <AlertCircle
              size={20}
              className="shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <p className="flex-1 text-sm">{entry.message}</p>
            <button
              onClick={() => dismiss(entry.id)}
              className="shrink-0 rounded p-0.5 text-red-200 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-red-400"
              aria-label="Dismiss error"
              data-testid={`mutation-error-${entry.id}-dismiss`}
            >
              <X size={16} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

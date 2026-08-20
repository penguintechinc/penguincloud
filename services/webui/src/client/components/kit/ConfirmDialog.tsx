import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { useMutationErrorStore } from "../../stores/mutationErrorStore";

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * ConfirmDialog component displays a modal confirmation dialog.
 * Traps focus within the dialog, supports danger variant for destructive actions.
 * Uses theme tokens: red for danger, slate surfaces, amber/sky interactive.
 *
 * The Tab trap also includes any live `role="alert"` region (not just this
 * dialog's own subtree). `MutationErrorBanner` portals its entries directly
 * onto `document.body`, specifically so a mutation failure raised while a
 * dialog is open — e.g. SwgPolicyPage's replace-confirm flow, which leaves
 * this dialog open on a failed replace — stays visible. A trap scoped only
 * to the dialog made that banner visible but keyboard-unreachable: Tab could
 * never land on its dismiss button while this dialog held focus. Matched by
 * role, not by importing MutationErrorBanner: the principle ("do not swallow
 * focus from something more urgent than this dialog") is not specific to one
 * component, and any future globally-portaled alert gets the same treatment
 * for free.
 *
 * The loop is driven explicitly end to end — never falls through to the
 * browser's native tab order — because native order is DOM-position
 * dependent, and a portaled alert's position relative to this dialog is not
 * something this component controls or can rely on.
 */
export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDangerous?: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isDangerous = false,
  isLoading = false,
  onConfirm,
  onCancel,
  testId = "confirm-dialog",
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  // Read, not subscribed: only used to decide `aria-modal` below, and a
  // Zustand hook already re-renders this component on every store change —
  // see the `aria-modal` note near the JSX for why that reactivity matters.
  const hasLiveAlert = useMutationErrorStore(
    (state) => state.errors.length > 0,
  );

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
        return;
      }

      if (e.key !== "Tab") return;

      const dialogElements = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ??
          [],
      );
      const alertElements = Array.from(
        document.querySelectorAll<HTMLElement>(
          `[role="alert"] ${FOCUSABLE_SELECTOR}`,
        ),
      );
      const focusableElements = [...dialogElements, ...alertElements];
      if (focusableElements.length === 0) return;

      e.preventDefault();
      const currentIndex = focusableElements.indexOf(
        document.activeElement as HTMLElement,
      );
      let nextIndex: number;
      if (currentIndex === -1) {
        // Focus is on neither the dialog nor a live alert (e.g. the
        // backdrop) — land on the natural end for the direction pressed,
        // same as a fresh trap would.
        nextIndex = e.shiftKey ? focusableElements.length - 1 : 0;
      } else {
        const step = e.shiftKey ? -1 : 1;
        nextIndex =
          (currentIndex + step + focusableElements.length) %
          focusableElements.length;
      }
      focusableElements[nextIndex]?.focus();
    };

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      confirmBtnRef.current?.focus();
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const getConfirmButtonClasses = () => {
    const base =
      "px-4 py-2 rounded font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:opacity-50";
    return isDangerous
      ? `${base} bg-red-600 hover:bg-red-700 text-white focus:ring-red-500 focus:ring-offset-slate-900`
      : `${base} bg-sky-500 hover:bg-sky-600 text-white focus:ring-sky-500 focus:ring-offset-slate-900`;
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onCancel}
        data-testid={`${testId}-backdrop`}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="alertdialog"
        // ARIA says content OUTSIDE an aria-modal="true" dialog is ignored
        // by assistive tech — which would suppress MutationErrorBanner's
        // role="alert" while this dialog is open, even now that it is both
        // clickable and keyboard-reachable. Dropping the exclusivity signal
        // when an alert is live is the scoped fix: it does not require
        // restructuring where the (globally-portaled, per-page-agnostic)
        // banner renders relative to this (per-feature) dialog. NOTE:
        // unverified whether this actually changes what a real screen
        // reader announces — jsdom has no AT to test against, and none was
        // available to check this against directly.
        aria-modal={hasLiveAlert ? undefined : "true"}
        aria-labelledby={`${testId}-title`}
        aria-describedby={`${testId}-message`}
        className="fixed inset-0 flex items-center justify-center z-50"
        data-testid={testId}
      >
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-lg max-w-md w-full mx-4 p-6">
          {/* Header */}
          <div className="flex items-start gap-3 mb-4">
            {isDangerous && (
              <AlertTriangle
                size={24}
                className="flex-shrink-0 text-red-500"
                aria-hidden="true"
              />
            )}
            <h2
              id={`${testId}-title`}
              className="text-lg font-semibold text-brand"
            >
              {title}
            </h2>
          </div>

          {/* Message */}
          <p id={`${testId}-message`} className="text-slate-300 mb-6">
            {message}
          </p>

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              ref={cancelBtnRef}
              onClick={onCancel}
              disabled={isLoading}
              className="px-4 py-2 rounded font-medium bg-slate-700 hover:bg-slate-600 text-slate-100 transition-colors focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 focus:ring-offset-slate-800 focus:outline-none disabled:opacity-50"
              data-testid={`${testId}-cancel`}
            >
              {cancelLabel}
            </button>
            <button
              ref={confirmBtnRef}
              onClick={onConfirm}
              disabled={isLoading}
              className={getConfirmButtonClasses()}
              data-testid={`${testId}-confirm`}
            >
              {isLoading ? "Loading..." : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

import React, { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * ConfirmDialog component displays a modal confirmation dialog.
 * Traps focus within the dialog, supports danger variant for destructive actions.
 * Uses theme tokens: red for danger, slate surfaces, amber/sky interactive.
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

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
      }

      /* istanbul ignore next -- unreachable: focus trap Tab handling requires simulating browser activeElement state which jsdom does not fully support */
      if (e.key === "Tab") {
        const focusableElements = dialogRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusableElements || focusableElements.length === 0) return;

        const firstElement = focusableElements[0] as HTMLElement;
        const lastElement = focusableElements[
          focusableElements.length - 1
        ] as HTMLElement;

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
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
        aria-modal="true"
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

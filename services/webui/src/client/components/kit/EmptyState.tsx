import { ReactNode } from "react";

/**
 * EmptyState component displays when no data is available.
 * Shows an icon, message, and optional action button.
 * Uses theme tokens: amber headings, slate text, sky interactive.
 */
export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    variant?: "primary" | "secondary";
  };
  dataTestId?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  dataTestId = "empty-state",
}: EmptyStateProps) {
  const getButtonClasses = (variant: "primary" | "secondary" = "primary") => {
    const base =
      "px-4 py-2 rounded font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 focus:outline-none";
    return variant === "primary"
      ? `${base} bg-sky-500 hover:bg-sky-600 text-white focus:ring-sky-500`
      : `${base} bg-slate-700 hover:bg-slate-600 text-slate-100 focus:ring-slate-500`;
  };

  return (
    <div
      data-testid={dataTestId}
      className="flex flex-col items-center justify-center py-12 px-4"
      role="region"
      aria-label="Empty state"
    >
      {icon && (
        <div className="mb-4 text-slate-500" aria-hidden="true">
          {icon}
        </div>
      )}

      <h3 className="text-lg font-semibold text-brand mb-2">{title}</h3>

      {description && (
        <p className="text-slate-400 text-center max-w-md mb-6">
          {description}
        </p>
      )}

      {action && (
        <button
          onClick={action.onClick}
          className={getButtonClasses(action.variant)}
          data-testid="empty-state-action"
          aria-label={action.label}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

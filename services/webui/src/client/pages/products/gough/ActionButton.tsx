interface ActionButtonProps {
  label: string;
  onClick: () => void;
  testId: string;
  /** `danger` for anything that destroys, drains or cuts off a resource. */
  variant?: "primary" | "danger" | "ghost";
  disabled?: boolean;
}

const VARIANTS: Record<string, string> = {
  primary:
    "bg-sky-500 hover:bg-sky-600 text-white focus:ring-sky-500 px-3 py-1.5 text-sm",
  danger:
    "bg-red-600 hover:bg-red-700 text-white focus:ring-red-500 px-3 py-1.5 text-sm",
  ghost:
    "border border-slate-600 text-amber-500 hover:text-amber-400 focus:ring-sky-500 px-2 py-1 text-xs",
};

/**
 * Button used by the Gough drawers and toolbars.
 *
 * Exists so the three screens share one set of variant styles: the danger
 * variant is what visually separates "deploy this rack" from "open details",
 * and a hand-written className per call site is how that distinction quietly
 * stops being applied on the fourth screen.
 */
export function ActionButton({
  label,
  onClick,
  testId,
  variant = "primary",
  disabled = false,
}: ActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className={`rounded transition-colors focus:ring-2 focus:outline-none disabled:opacity-50 ${VARIANTS[variant]}`}
    >
      {label}
    </button>
  );
}

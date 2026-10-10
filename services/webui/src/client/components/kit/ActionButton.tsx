/**
 * Button used by product drawers and toolbars.
 *
 * Promoted here from `pages/products/gough/ActionButton.tsx` and
 * `pages/products/nest/NestUi.tsx`, which were byte-identical apart from a
 * docstring. Both files said the duplication was "deliberate and bounded: on a
 * THIRD product needing them these belong in `components/kit`, where the
 * variant styles and the absent-value rendering can be asserted once". This is
 * that third product.
 *
 * The variant styles are the reason it is a component rather than a className:
 * `danger` is what visually separates "publish this block page to every user"
 * from "open details", and a hand-written class per call site is how that
 * distinction quietly stops being applied on the next screen.
 */

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  testId: string;
  /** `danger` for anything that destroys, overwrites or cuts off a resource. */
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

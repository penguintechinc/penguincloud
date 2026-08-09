/**
 * Small presentational atoms shared by the Nest screens.
 *
 * These mirror the Gough equivalents (`gough/ActionButton.tsx`,
 * `gough/FactList.tsx`) rather than importing them, because those bake Gough's
 * own `data-testid` values in and reaching across product directories couples
 * two screens that have no reason to change together.
 *
 * The duplication is deliberate and bounded: on a THIRD product needing them
 * these belong in `components/kit`, where the variant styles and the
 * absent-value rendering can be asserted once. Two copies is not yet that.
 */

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  testId: string;
  /** `danger` for anything that destroys or overwrites data. */
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

/** Button used by the Nest drawers and toolbars. */
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

/** One labelled fact. A null/empty value renders as a dash, never blank. */
export type Fact = [label: string, value: string | null | undefined];

/**
 * Definition list used by the Nest detail drawer.
 *
 * A blank cell reads as a layout bug; a dash reads as "the product did not
 * report one", which is the true statement.
 */
export function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="grid grid-cols-2 gap-y-2 text-sm" data-testid="nest-facts">
      {facts.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-slate-400">{label}</dt>
          <dd className="text-slate-200">{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

interface RowOpenButtonsProps<T extends { id: string }> {
  rows: T[];
  label: (row: T) => string;
  onOpen: (row: T) => void;
  testIdPrefix: string;
}

/**
 * Per-row buttons that open the detail drawer.
 *
 * A button column rather than a clickable table row: a click target spanning
 * the whole row is invisible to a keyboard user and unreachable by tab, so the
 * drawer would be mouse-only.
 */
export function RowOpenButtons<T extends { id: string }>({
  rows,
  label,
  onOpen,
  testIdPrefix,
}: RowOpenButtonsProps<T>) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          onClick={() => onOpen(row)}
          data-testid={`${testIdPrefix}-${row.id}`}
          className="px-2 py-1 text-xs rounded border border-slate-600 text-amber-500 hover:text-amber-400 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none"
        >
          {label(row)}
        </button>
      ))}
    </div>
  );
}

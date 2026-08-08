/** One labelled fact. A null/empty value renders as a dash, never blank. */
export type Fact = [label: string, value: string | null | undefined];

/**
 * Definition list used by every Gough DetailDrawer overview tab.
 *
 * Shared so the three screens cannot drift into three different renderings of
 * "an absent value" — a blank cell reads as a layout bug, a dash reads as
 * "this product did not report one".
 */
export function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="grid grid-cols-2 gap-y-2 text-sm" data-testid="gough-facts">
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
 * the whole row is invisible to a keyboard user and unreachable by tab, so
 * the drawer would be mouse-only.
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

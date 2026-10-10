/**
 * Per-row buttons that open a detail drawer.
 *
 * Promoted from the Gough and Nest copies on the third product needing it.
 *
 * A button column rather than a clickable table row: a click target spanning
 * the whole row is invisible to a keyboard user and unreachable by tab, so the
 * drawer would be mouse-only. Keeping that decision in one component is the
 * point — it is the kind of thing a new screen re-implements as an `onClick`
 * on `<tr>` without noticing what it has removed.
 */

interface RowOpenButtonsProps<T extends { id: string }> {
  rows: T[];
  label: (row: T) => string;
  onOpen: (row: T) => void;
  testIdPrefix: string;
}

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

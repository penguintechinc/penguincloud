/**
 * Pagination controls for DataTable.
 *
 * Split out of DataTable to keep every kit file under the 5,000-character
 * house limit. Renders nothing when there is only one page.
 */

export interface DataTablePaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const BUTTON_CLASS =
  "px-3 py-1 bg-slate-700 hover:bg-sky-500 disabled:opacity-50 text-white " +
  "rounded text-sm font-medium transition-colors focus:ring-2 focus:ring-sky-500 " +
  "focus:ring-offset-2 focus:ring-offset-slate-800";

export function DataTablePagination({
  currentPage,
  totalPages,
  onPageChange,
}: DataTablePaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div
      data-testid="datatable-pagination"
      className="flex items-center justify-between mt-4 px-4 py-3 bg-slate-800 rounded-lg border border-slate-700"
    >
      <span className="text-slate-300 text-sm" role="status" aria-live="polite">
        Page {currentPage} of {totalPages}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className={BUTTON_CLASS}
          aria-label="Previous page"
          data-testid="datatable-prev"
        >
          Prev
        </button>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className={BUTTON_CLASS}
          aria-label="Next page"
          data-testid="datatable-next"
        >
          Next
        </button>
      </div>
    </div>
  );
}

/**
 * Provider rollup: customers down the rows, products across the columns.
 * Rendered only in provider scope; fed by GET /api/v1/dashboard/rollup.
 */

import { DataTable, type ColumnConfig } from "../../components/kit/DataTable";
import StatusBadge from "../../components/kit/StatusBadge";
import { EmptyState } from "../../components/kit/EmptyState";
import {
  rollupProductColumns,
  toMatrixRows,
  type MatrixCell,
  type MatrixRow,
} from "./rollupMatrix";
import type { DashboardRollupRow } from "../../types";

interface RollupMatrixProps {
  rows: DashboardRollupRow[];
  isLoading: boolean;
  error: Error | null;
  onRetry?: () => void;
}

function StatusCell({
  value,
  product,
}: {
  value: MatrixCell;
  product: string;
}) {
  if (!value) {
    return (
      <span className="text-slate-600" aria-label={`${product}: not connected`}>
        —
      </span>
    );
  }
  return <StatusBadge status={value} size="sm" />;
}

export default function RollupMatrix({
  rows,
  isLoading,
  error,
  onRetry,
}: RollupMatrixProps) {
  const products = rollupProductColumns(rows);
  const matrixRows = toMatrixRows(rows, products);

  if (!isLoading && !error && products.length === 0) {
    return (
      <EmptyState
        title="No customer products"
        description="Customer tenants have no product connections registered yet."
        dataTestId="rollup-empty"
      />
    );
  }

  const columns: ColumnConfig<MatrixRow>[] = [
    { key: "tenant", label: "Customer", sortable: true },
    ...products.map<ColumnConfig<MatrixRow>>((product) => ({
      key: product,
      label: product,
      sortable: false,
      render: (value) => (
        <StatusCell value={value as MatrixCell} product={product} />
      ),
    })),
  ];

  return (
    <div data-testid="rollup-matrix">
      <DataTable
        columns={columns}
        data={matrixRows}
        isLoading={isLoading}
        error={error}
        onRetry={onRetry}
        caption="Customer tenants by product status"
      />
    </div>
  );
}

/**
 * Reshapes the provider rollup response into a customers × products matrix.
 *
 * The API returns one row per customer with a variable-length product list;
 * the table needs a fixed column per product across all customers, with an
 * explicit gap where a customer does not have that product connected.
 */

import type { DashboardRollupRow, HealthStatus } from "../../types";

/** A cell value: a status, or absent when the customer lacks that product. */
export type MatrixCell = HealthStatus | null;

/**
 * Product columns are spread onto the row itself rather than nested, so each
 * DataTable column can carry a distinct key (nested cells would make every
 * product column share one key and collide as React children).
 */
export type MatrixRow = {
  id: string;
  tenant: string;
} & Record<string, string | MatrixCell>;

/** Column keys that are not products. */
export const RESERVED_MATRIX_KEYS = ["id", "tenant"];

/**
 * The union of every product name in the response, sorted so column order is
 * stable between renders regardless of per-tenant ordering.
 */
export function rollupProductColumns(rows: DashboardRollupRow[]): string[] {
  const products = new Set<string>();
  rows.forEach((row) => row.products.forEach((p) => products.add(p.product)));
  return [...products].sort();
}

/** One matrix row per customer tenant, with a cell for every product column. */
export function toMatrixRows(
  rows: DashboardRollupRow[],
  columns: string[],
): MatrixRow[] {
  return rows.map((row) => {
    const byProduct = new Map(row.products.map((p) => [p.product, p.status]));
    const matrixRow: MatrixRow = {
      id: String(row.tenant_id),
      tenant: row.tenant_name,
    };
    columns.forEach((product) => {
      matrixRow[product] = byProduct.get(product) ?? null;
    });
    return matrixRow;
  });
}

/**
 * Provider rollup matrix tests, including the reshaping helpers.
 *
 * The fixture is the MSW rollup fixture, so these also pin the response shape
 * the matrix expects against the Task 2B contract.
 */

import { render, screen } from "@testing-library/react";
import RollupMatrix from "../RollupMatrix";
import { rollupProductColumns, toMatrixRows } from "../rollupMatrix";
import { MOCK_DASHBOARD_ROLLUP } from "../../../mocks/fixtures";

// No cast needed: MockDashboardRollup and DashboardRollupRow are now
// structurally identical (connection_id: number in both, matching the
// generated schema's RollupProduct) — a `MockDashboardRollup[] as unknown as
// DashboardRollupRow[]` here would silently mask the two drifting again.
const rows = MOCK_DASHBOARD_ROLLUP;

describe("rollupProductColumns", () => {
  it("unions every product across tenants, sorted", () => {
    expect(rollupProductColumns(rows)).toEqual([
      "elder",
      "gough",
      "nest",
      "tobogganing",
      "waddleai",
      "waddlebot",
    ]);
  });

  it("returns nothing for an empty rollup", () => {
    expect(rollupProductColumns([])).toEqual([]);
  });
});

describe("toMatrixRows", () => {
  const columns = rollupProductColumns(rows);
  const matrix = toMatrixRows(rows, columns);

  it("produces one row per customer tenant", () => {
    expect(matrix).toHaveLength(rows.length);
    expect(matrix[0].tenant).toBe("Acme Production");
  });

  it("keys rows by tenant id as a string", () => {
    expect(matrix[0].id).toBe("11");
  });

  it("fills a cell for every column, null where not connected", () => {
    const acme = matrix[0];
    expect(acme.gough).toBe("healthy");
    expect(acme.waddleai).toBe("degraded");
    expect(acme.tobogganing).toBeNull();
  });

  it("carries a non-healthy status through unchanged", () => {
    const research = matrix.find((r) => r.id === "14");
    expect(research?.elder).toBe("unhealthy");
  });
});

describe("RollupMatrix", () => {
  it("renders a column per product plus the customer column", () => {
    render(<RollupMatrix rows={rows} isLoading={false} error={null} />);

    expect(screen.getByTestId("rollup-matrix")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /customer/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "gough" }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("datatable-row")).toHaveLength(rows.length);
  });

  it("renders a status badge per connected product", () => {
    render(<RollupMatrix rows={rows} isLoading={false} error={null} />);

    expect(screen.getAllByText("Healthy").length).toBeGreaterThan(0);
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Unhealthy")).toBeInTheDocument();
  });

  it("marks products a customer does not have", () => {
    render(<RollupMatrix rows={rows} isLoading={false} error={null} />);

    expect(screen.getAllByLabelText(/not connected$/).length).toBeGreaterThan(
      0,
    );
  });

  it("shows an empty state when no customer has products", () => {
    render(
      <RollupMatrix
        rows={[{ tenant_id: 99, tenant_name: "Solo", products: [] }]}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByTestId("rollup-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("rollup-matrix")).not.toBeInTheDocument();
  });

  it("defers to the table's loading state rather than the empty state", () => {
    render(<RollupMatrix rows={[]} isLoading error={null} />);

    expect(screen.queryByTestId("rollup-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("rollup-matrix")).toBeInTheDocument();
  });

  it("defers to the table's error state rather than the empty state", () => {
    const onRetry = jest.fn();
    render(
      <RollupMatrix
        rows={[]}
        isLoading={false}
        error={new Error("rollup failed")}
        onRetry={onRetry}
      />,
    );

    expect(screen.queryByTestId("rollup-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("rollup-matrix")).toBeInTheDocument();
  });
});

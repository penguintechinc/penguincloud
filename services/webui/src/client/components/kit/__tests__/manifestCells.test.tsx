/**
 * The cell registry: one exhaustive check per `CellKind`, plus the
 * `absent_as` modes and the "unknown kind degrades to text, logs once"
 * fallback Design §3.4 requires.
 */
import { render, screen } from "@testing-library/react";
import { renderCell, resetUnknownCellKindWarnings } from "../manifestCells";
import type { ColumnSpec } from "../manifestTypes";

function column(
  overrides: Partial<ColumnSpec> & Pick<ColumnSpec, "cell">,
): ColumnSpec {
  return {
    field: "value",
    label: "Value",
    sortable: false,
    ...overrides,
  };
}

beforeEach(() => {
  resetUnknownCellKindWarnings();
  jest.restoreAllMocks();
});

describe("renderCell — absent_as modes", () => {
  it.each([
    ["dash", "—"],
    [undefined, "—"],
    ["literal:Everyone", "Everyone"],
  ] as const)(
    "absent_as=%s renders %s for a null value",
    (absentAs, expected) => {
      const col = column({
        cell: { kind: "text", styles: [], relative: false },
        absent_as: absentAs,
      });
      render(<div>{renderCell(col, { value: null })}</div>);
      expect(screen.getByText(expected)).toBeInTheDocument();
    },
  );

  it("absent_as=zero renders a real 0, distinct from the dash", () => {
    const col = column({
      cell: { kind: "count", styles: [], relative: false },
      absent_as: "zero",
    });
    render(<div>{renderCell(col, { value: undefined })}</div>);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("a real zero is rendered as a fact, not absence — the money regression this schema names", () => {
    const col = column({
      cell: {
        kind: "money",
        styles: [],
        relative: false,
        currency_field: "currency",
      },
      absent_as: "dash",
    });
    render(<div>{renderCell(col, { value: 0, currency: "USD" })}</div>);
    expect(screen.getByText("0.00 USD")).toBeInTheDocument();
  });
});

describe("renderCell — each CellKind", () => {
  it("text", () => {
    const col = column({ cell: { kind: "text", styles: [], relative: false } });
    render(<div>{renderCell(col, { value: "hello" })}</div>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("enum_badge — known style", () => {
    const col = column({
      cell: {
        kind: "enum_badge",
        styles: [{ value: "healthy", style: "success" }],
        relative: false,
      },
    });
    render(<div>{renderCell(col, { value: "healthy" })}</div>);
    expect(screen.getByText("healthy")).toHaveClass("text-emerald-400");
  });

  it("enum_badge — unrecognised style degrades to neutral, never crashes", () => {
    const col = column({
      cell: {
        kind: "enum_badge",
        styles: [{ value: "x", style: "mystery" }],
        relative: false,
      },
    });
    render(<div>{renderCell(col, { value: "x" })}</div>);
    expect(screen.getByText("x")).toHaveClass("text-slate-400");
  });

  it("enum_badge — a value with no matching style entry also degrades to neutral", () => {
    const col = column({
      cell: { kind: "enum_badge", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "unmapped" })}</div>);
    expect(screen.getByText("unmapped")).toHaveClass("text-slate-400");
  });

  it("tags — renders each tag", () => {
    const col = column({ cell: { kind: "tags", styles: [], relative: false } });
    render(<div>{renderCell(col, { value: ["gpu", "edge"] })}</div>);
    expect(screen.getByText("gpu")).toBeInTheDocument();
    expect(screen.getByText("edge")).toBeInTheDocument();
  });

  it("tags — an empty (but present) array renders as absent, matching nodeColumns.tsx", () => {
    const col = column({
      cell: { kind: "tags", styles: [], relative: false },
      absent_as: "dash",
    });
    render(<div>{renderCell(col, { value: [] })}</div>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("tags — a non-array value degrades to absent rather than crashing", () => {
    const col = column({
      cell: { kind: "tags", styles: [], relative: false },
      absent_as: "dash",
    });
    render(<div>{renderCell(col, { value: "not-an-array" })}</div>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("number — with unit", () => {
    const col = column({
      cell: { kind: "number", styles: [], relative: false, unit: "cores" },
    });
    render(<div>{renderCell(col, { value: 8 })}</div>);
    expect(screen.getByText("8 cores")).toBeInTheDocument();
  });

  it("number — no unit", () => {
    const col = column({
      cell: { kind: "number", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: 8 })}</div>);
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("bytes — formats to a human unit", () => {
    const col = column({
      cell: { kind: "bytes", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: 1536 })}</div>);
    expect(screen.getByText("1.5 KB")).toBeInTheDocument();
  });

  it("bytes — sub-KB values stay in whole bytes", () => {
    const col = column({
      cell: { kind: "bytes", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: 512 })}</div>);
    expect(screen.getByText("512 B")).toBeInTheDocument();
  });

  it("bytes — negative values keep the sign", () => {
    const col = column({
      cell: { kind: "bytes", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: -2048 })}</div>);
    expect(screen.getByText("-2.0 KB")).toBeInTheDocument();
  });

  it("bytes — a non-numeric value renders verbatim rather than crashing", () => {
    const col = column({
      cell: { kind: "bytes", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "not-a-number" })}</div>);
    expect(screen.getByText("not-a-number")).toBeInTheDocument();
  });

  it("money — value plus the sibling currency field", () => {
    const col = column({
      cell: {
        kind: "money",
        styles: [],
        relative: false,
        currency_field: "currency",
      },
    });
    render(<div>{renderCell(col, { value: 42.5, currency: "USD" })}</div>);
    expect(screen.getByText("42.50 USD")).toBeInTheDocument();
  });

  it("money — no currency_field declared renders the amount alone", () => {
    const col = column({
      cell: { kind: "money", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: 42.5 })}</div>);
    expect(screen.getByText("42.50")).toBeInTheDocument();
  });

  it("money — a non-numeric value renders verbatim rather than crashing", () => {
    const col = column({
      cell: { kind: "money", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "not-a-number" })}</div>);
    expect(screen.getByText("not-a-number")).toBeInTheDocument();
  });

  it("timestamp — relative, seconds", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    render(
      <div>
        {renderCell(col, {
          value: new Date(Date.now() - 30 * 1000).toISOString(),
        })}
      </div>,
    );
    expect(screen.getByText("30s ago")).toBeInTheDocument();
  });

  it("timestamp — relative, minutes", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    render(<div>{renderCell(col, { value: fiveMinutesAgo })}</div>);
    expect(screen.getByText("5m ago")).toBeInTheDocument();
  });

  it("timestamp — relative, hours", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    render(
      <div>
        {renderCell(col, {
          value: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
        })}
      </div>,
    );
    expect(screen.getByText("3h ago")).toBeInTheDocument();
  });

  it("timestamp — relative, days", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    render(
      <div>
        {renderCell(col, {
          value: new Date(Date.now() - 2 * 86400 * 1000).toISOString(),
        })}
      </div>,
    );
    expect(screen.getByText("2d ago")).toBeInTheDocument();
  });

  it("timestamp — relative, a future timestamp reads 'from now'", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    render(
      <div>
        {renderCell(col, {
          value: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        })}
      </div>,
    );
    expect(screen.getByText("5m from now")).toBeInTheDocument();
  });

  it("timestamp — relative, an unparseable value falls back to the raw string", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: true },
    });
    render(<div>{renderCell(col, { value: "not-a-date" })}</div>);
    expect(screen.getByText("not-a-date")).toBeInTheDocument();
  });

  it("timestamp — absolute", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "2026-01-01T00:00:00Z" })}</div>);
    expect(
      screen.getByText(new Date("2026-01-01T00:00:00Z").toLocaleString()),
    ).toBeInTheDocument();
  });

  it("timestamp — absolute, an unparseable value falls back to the raw string", () => {
    const col = column({
      cell: { kind: "timestamp", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "not-a-date" })}</div>);
    expect(screen.getByText("not-a-date")).toBeInTheDocument();
  });

  it("boolean — true/false labels", () => {
    const col = column({
      cell: {
        kind: "boolean",
        styles: [],
        relative: false,
        labels: { true_label: "Active", false_label: "Inactive" },
      },
    });
    render(<div>{renderCell(col, { value: true })}</div>);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("boolean — false renders the false label, not the true one", () => {
    const col = column({
      cell: {
        kind: "boolean",
        styles: [],
        relative: false,
        labels: { true_label: "Active", false_label: "Inactive" },
      },
    });
    render(<div>{renderCell(col, { value: false })}</div>);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("boolean — no labels declared falls back to the literal True/False", () => {
    const col = column({
      cell: { kind: "boolean", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: true })}</div>);
    expect(screen.getByText("True")).toBeInTheDocument();

    const colFalse = column({
      cell: { kind: "boolean", styles: [], relative: false },
    });
    render(<div>{renderCell(colFalse, { value: false })}</div>);
    expect(screen.getByText("False")).toBeInTheDocument();
  });

  it("boolean — a non-boolean upstream value is rendered, not discarded", () => {
    const col = column({
      cell: {
        kind: "boolean",
        styles: [],
        relative: false,
        labels: { true_label: "Active", false_label: "Inactive" },
      },
    });
    render(<div>{renderCell(col, { value: "maybe" })}</div>);
    expect(screen.getByText("maybe")).toBeInTheDocument();
  });

  it("link — renders the id field as text, no navigation (item-path gap)", () => {
    const col = column({
      cell: {
        kind: "link",
        styles: [],
        relative: false,
        to_kind: "nodes",
        id_field: "node_id",
      },
    });
    render(<div>{renderCell(col, { value: "ignored", node_id: "n-1" })}</div>);
    expect(screen.getByText("n-1")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("link — falls back to the raw value when no id_field is declared", () => {
    const col = column({
      cell: { kind: "link", styles: [], relative: false, to_kind: "nodes" },
    });
    render(<div>{renderCell(col, { value: "n-1" })}</div>);
    expect(screen.getByText("n-1")).toBeInTheDocument();
  });

  it("link — falls back to the raw value when id_field names a key the row lacks", () => {
    const col = column({
      cell: {
        kind: "link",
        styles: [],
        relative: false,
        to_kind: "nodes",
        id_field: "missing",
      },
    });
    render(<div>{renderCell(col, { value: "n-1" })}</div>);
    expect(screen.getByText("n-1")).toBeInTheDocument();
  });

  it("count — array length", () => {
    const col = column({
      cell: { kind: "count", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: ["a", "b", "c"] })}</div>);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("count — a bare number is rendered as-is", () => {
    const col = column({
      cell: { kind: "count", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: 4 })}</div>);
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("count — a malformed (non-array, non-number) value degrades to 0 rather than crashing", () => {
    const col = column({
      cell: { kind: "count", styles: [], relative: false },
    });
    render(<div>{renderCell(col, { value: "not-a-count" })}</div>);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});

describe("renderCell — unknown kind", () => {
  it("degrades to text and logs exactly once per kind", () => {
    const errorSpy = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const col = column({
      cell: { kind: "sparkline", styles: [], relative: false },
    });

    const { unmount } = render(<div>{renderCell(col, { value: "raw" })}</div>);
    expect(screen.getByText("raw")).toBeInTheDocument();
    unmount();
    render(<div>{renderCell(col, { value: "raw-again" })}</div>);

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0][0]).toContain("sparkline");
  });
});

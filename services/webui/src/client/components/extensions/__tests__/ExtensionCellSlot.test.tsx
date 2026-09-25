/**
 * `renderCellSlot` — the cell-slot lookup + render decision, in isolation
 * from `ManifestResourceScreen`'s column building. Fixtures use an invented
 * product type/resource so a passing suite cannot be explained by a hidden
 * per-product branch in the resolver itself — mirrors
 * `ExtensionSlotRenderer.test.tsx`'s own discipline for page slots.
 */
import { render, screen } from "@testing-library/react";
import { renderCellSlot } from "../ExtensionCellSlot";
import {
  registerCellExtension,
  clearCellExtensions,
  type ExtensionCellComponent,
} from "../ExtensionCellRegistry";
import type { ColumnSpec, ExtensionSlot } from "../../kit/manifestTypes";

const column: ColumnSpec = {
  field: "scope_id",
  label: "Scope",
  cell: { kind: "text", styles: [], relative: false },
  sortable: false,
};

const slot: ExtensionSlot = {
  slot: "cell",
  id: "scope_id",
  label: "Scope Cell",
  resource: "cell-slot-resource",
  position: 0,
};

const SyntheticCell: ExtensionCellComponent = ({ value }) => (
  <span data-testid="synthetic-cell">{String(value)}</span>
);

afterEach(() => {
  clearCellExtensions();
});

it("renders the registered component when a cell slot matches AND is registered", () => {
  registerCellExtension("cell-slot-product", "scope_id", SyntheticCell);

  render(
    <>
      {renderCellSlot(
        "cell-slot-product",
        [slot],
        "cell-slot-resource",
        column,
        { scope_id: "team-42" },
      )}
    </>,
  );

  expect(screen.getByTestId("synthetic-cell")).toHaveTextContent("team-42");
});

it("degrades to the default renderCell output when a slot is declared but NOT registered", () => {
  render(
    <>
      {renderCellSlot(
        "unregistered-product",
        [slot],
        "cell-slot-resource",
        column,
        { scope_id: "team-42" },
      )}
    </>,
  );

  expect(screen.queryByTestId("synthetic-cell")).not.toBeInTheDocument();
  expect(screen.getByText("team-42")).toBeInTheDocument();
});

it("degrades to the default renderCell output when no extension slot matches this resource/column at all", () => {
  registerCellExtension("cell-slot-product", "scope_id", SyntheticCell);

  render(
    <>
      {renderCellSlot("cell-slot-product", [], "cell-slot-resource", column, {
        scope_id: "team-42",
      })}
    </>,
  );

  expect(screen.queryByTestId("synthetic-cell")).not.toBeInTheDocument();
  expect(screen.getByText("team-42")).toBeInTheDocument();
});

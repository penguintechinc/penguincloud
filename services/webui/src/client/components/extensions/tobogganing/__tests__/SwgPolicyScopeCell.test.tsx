/**
 * `SwgPolicyScopeCell` in isolation from `ManifestResourceScreen` — the
 * three-way branch (`value` present / absent+tenant / absent+non-tenant)
 * `ManifestResourceScreen.tobogganing.equivalence.test.tsx`'s golden fixtures
 * only exercise two of: that file always pairs a null `scope_id` with
 * `scope: "tenant"` and a present `scope_id` with a non-tenant scope, never
 * the null-scope_id-AND-non-tenant-scope combination this component must
 * still degrade to a dash for.
 */
import { render, screen } from "@testing-library/react";
import { SwgPolicyScopeCell } from "../SwgPolicyScopeCell";
import type { ColumnSpec } from "../../../kit/manifestTypes";

const column: ColumnSpec = {
  field: "scope_id",
  label: "Applies to",
  cell: { kind: "text", styles: [], relative: false },
  sortable: false,
  absent_as: "dash",
};

it("renders the raw value verbatim when scope_id is present, regardless of scope", () => {
  render(
    <SwgPolicyScopeCell
      row={{ scope: "group", scope_id: "grp-eng" }}
      value="grp-eng"
      column={column}
    />,
  );

  expect(screen.getByText("grp-eng")).toBeInTheDocument();
});

it('renders "Everyone" when scope_id is absent AND scope is "tenant"', () => {
  render(
    <SwgPolicyScopeCell
      row={{ scope: "tenant", scope_id: null }}
      value={null}
      column={column}
    />,
  );

  expect(screen.getByText("Everyone")).toBeInTheDocument();
});

it('renders a dash when scope_id is absent AND scope is NOT "tenant" — never a blank cell', () => {
  render(
    <SwgPolicyScopeCell
      row={{ scope: "group", scope_id: null }}
      value={null}
      column={column}
    />,
  );

  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.queryByText("Everyone")).not.toBeInTheDocument();
});

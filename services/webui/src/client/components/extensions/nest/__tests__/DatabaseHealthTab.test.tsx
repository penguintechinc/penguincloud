/**
 * Nest's Health `detail_tab` extension — must render the same six facts
 * `DatabaseTabs.tsx`'s hand-written "health" tab does, off the raw manifest
 * row rather than a typed `NestDatabase`.
 */
import { render, screen, within } from "@testing-library/react";
import type { ExtensionSlot } from "../../../kit/manifestTypes";
import type { ManifestRow } from "../../../kit/manifestCells";
import DatabaseHealthTab from "../DatabaseHealthTab";

const SLOT: ExtensionSlot = {
  slot: "detail_tab",
  id: "health",
  label: "Health",
  resource: "database",
  position: 0,
};

function renderTab(row: ManifestRow) {
  return render(
    <DatabaseHealthTab
      productType="nest"
      productId={7}
      tenantId={42}
      row={row}
      slot={SLOT}
    />,
  );
}

it("renders every health fact reported on the row", () => {
  renderTab({
    healthState: "Healthy",
    healthMessage: "Probe succeeded",
    healthLastCheck: "2026-09-01T00:00:00Z",
    externalProvider: "aws",
    externalEndpoint: "db.example.com:5432",
    externalRegion: "us-east-1",
  });

  const facts = within(screen.getByTestId("nest-health-facts"));
  expect(facts.getByText("Healthy")).toBeInTheDocument();
  expect(facts.getByText("Probe succeeded")).toBeInTheDocument();
  expect(facts.getByText("2026-09-01T00:00:00Z")).toBeInTheDocument();
  expect(facts.getByText("aws")).toBeInTheDocument();
  expect(facts.getByText("db.example.com:5432")).toBeInTheDocument();
  expect(facts.getByText("us-east-1")).toBeInTheDocument();
});

it("renders a dash for every absent field instead of the literal string 'undefined'", () => {
  renderTab({});

  const facts = within(screen.getByTestId("nest-health-facts"));
  expect(facts.queryByText("undefined")).not.toBeInTheDocument();
  expect(facts.getAllByText("—").length).toBe(6);
});

it("stringifies a non-string field rather than dropping it", () => {
  // `ManifestRow` is `Record<string, unknown>` — a numeric or boolean value
  // reaching this row is not a type error, and must still render as text.
  renderTab({ healthState: true, healthLastCheck: 1735689600 });

  const facts = within(screen.getByTestId("nest-health-facts"));
  expect(facts.getByText("true")).toBeInTheDocument();
  expect(facts.getByText("1735689600")).toBeInTheDocument();
});

/**
 * `ExtensionDetailTabSlot` — the registry lookup + Suspense/fallback
 * decision for a `detail_tab` slot, in isolation from `ManifestResourceDetail`'s
 * tab assembly. Fixtures use an invented product type so a passing suite
 * cannot be explained by a hidden per-product branch here — mirrors
 * `ExtensionSlotRenderer.test.tsx`'s own discipline for page slots.
 */
import { render, screen } from "@testing-library/react";
import { ExtensionDetailTabSlot } from "../ExtensionDetailTabSlot";
import {
  registerDetailTabExtension,
  clearDetailTabExtensions,
  type ExtensionDetailTabProps,
} from "../ExtensionDetailTabRegistry";
import type { ExtensionSlot } from "../../kit/manifestTypes";

const slot: ExtensionSlot = {
  slot: "detail_tab",
  id: "health",
  label: "Health",
  resource: "databases",
  position: 0,
};

function SyntheticDetailTab(props: ExtensionDetailTabProps) {
  return (
    <div data-testid="synthetic-detail-tab">
      {props.productType}/{props.productId}/{props.tenantId}/{props.slot.id}/
      {String(props.row.id)}
    </div>
  );
}

afterEach(() => {
  clearDetailTabExtensions();
});

it("renders the registered component inside Suspense, passing productType/productId/tenantId/row/slot through unchanged", async () => {
  registerDetailTabExtension("detail-tab-product", "health", () =>
    Promise.resolve({ default: SyntheticDetailTab }),
  );

  render(
    <ExtensionDetailTabSlot
      productType="detail-tab-product"
      productId={11}
      tenantId={22}
      row={{ id: "db-1" }}
      slot={slot}
    />,
  );

  expect(await screen.findByTestId("synthetic-detail-tab")).toHaveTextContent(
    "detail-tab-product/11/22/health/db-1",
  );
});

it("renders the generic fallback, not the extension, when nothing is registered for this key", () => {
  render(
    <ExtensionDetailTabSlot
      productType="unregistered-product"
      productId={11}
      tenantId={22}
      row={{ id: "db-1" }}
      slot={slot}
    />,
  );

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
  expect(screen.queryByTestId("synthetic-detail-tab")).not.toBeInTheDocument();
});

it("falls back with the slot's own label in the message", () => {
  render(
    <ExtensionDetailTabSlot
      productType="unregistered-product"
      productId={11}
      tenantId={22}
      row={{ id: "db-1" }}
      slot={{ ...slot, label: "My Custom Label" }}
    />,
  );

  expect(screen.getByText(/My Custom Label/)).toBeInTheDocument();
});

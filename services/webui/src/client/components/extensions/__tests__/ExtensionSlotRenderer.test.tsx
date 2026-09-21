/**
 * `ExtensionSlotRenderer` — the registry lookup + Suspense/fallback decision
 * in isolation from routing. Fixtures use an invented product type so a
 * passing suite cannot be explained by a hidden per-product branch here.
 */
import { render, screen } from "@testing-library/react";
import { ExtensionSlotRenderer } from "../ExtensionSlotRenderer";
import {
  registerPageExtension,
  clearPageExtensions,
  type ExtensionPageProps,
} from "../ExtensionRegistry";
import type { ExtensionSlot } from "../../kit/manifestTypes";

const slot: ExtensionSlot = {
  slot: "page",
  id: "renderer-panel",
  label: "Renderer Panel",
  resource: null,
  position: 0,
};

function SyntheticExtension(props: ExtensionPageProps) {
  return (
    <div data-testid="synthetic-extension">
      {props.productType}/{props.productId}/{props.tenantId}/{props.slot.id}
    </div>
  );
}

afterEach(() => {
  clearPageExtensions();
});

it("renders the registered component inside Suspense, passing productType/productId/tenantId/slot through unchanged", async () => {
  registerPageExtension("renderer-product", "renderer-panel", () =>
    Promise.resolve({ default: SyntheticExtension }),
  );

  render(
    <ExtensionSlotRenderer
      productType="renderer-product"
      productId={11}
      tenantId={22}
      slot={slot}
    />,
  );

  expect(await screen.findByTestId("synthetic-extension")).toHaveTextContent(
    "renderer-product/11/22/renderer-panel",
  );
});

it("renders the generic fallback, not the extension, when nothing is registered for this key", () => {
  render(
    <ExtensionSlotRenderer
      productType="unregistered-product"
      productId={11}
      tenantId={22}
      slot={slot}
    />,
  );

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
  expect(screen.queryByTestId("synthetic-extension")).not.toBeInTheDocument();
});

it("falls back with the slot's own label in the message", () => {
  render(
    <ExtensionSlotRenderer
      productType="unregistered-product"
      productId={11}
      tenantId={22}
      slot={{ ...slot, label: "My Custom Label" }}
    />,
  );

  expect(screen.getByText(/My Custom Label/)).toBeInTheDocument();
});

/**
 * A defensive branch `ExtensionPageRoute` cannot reach through the normal
 * fetch chain: `useConsoleManifests` is `enabled: tenantId !== undefined`
 * (`components/kit/useConsoleManifests.ts`), so in practice an `entry` never
 * resolves while `tenantId` is `undefined`. The `tenantId === undefined`
 * arm of the guard exists purely so TypeScript can narrow `tenantId` from
 * `number | undefined` to `number` before it is handed to
 * `ExtensionSlotRenderer` — this test proves that arm degrades to the same
 * fallback rather than throwing or rendering with an invalid `tenantId`,
 * by mocking the two kit hooks directly instead of the fetch chain
 * `ExtensionPageRoute.test.tsx` exercises for real.
 */
import { render, screen } from "@testing-library/react";
import { useParams } from "react-router";
import { ExtensionPageRoute } from "../ExtensionPageRoute";
import type { ConsoleManifest, ExtensionSlot } from "../../kit/manifestTypes";

const mockUseActiveTenantId = jest.fn();
jest.mock("../../kit/useProductResource", () => ({
  useActiveTenantId: () => mockUseActiveTenantId(),
}));

const mockUseConsoleManifests = jest.fn();
jest.mock("../../kit/useConsoleManifests", () => ({
  useConsoleManifests: () => mockUseConsoleManifests(),
}));

const slot: ExtensionSlot = {
  slot: "page",
  id: "demo-panel",
  label: "Demo Panel",
  resource: null,
  position: 0,
};

const manifest: ConsoleManifest = {
  manifest_version: 2,
  product_type: "demo-product",
  display_name: "Demo Product",
  nav: { items: [] },
  resources: [],
  operations: null,
  metrics: null,
  extensions: [slot],
};

beforeEach(() => {
  jest.clearAllMocks();
  (useParams as jest.Mock).mockReturnValue({
    productType: "demo-product",
    extensionId: "demo-panel",
  });
  mockUseConsoleManifests.mockReturnValue({
    isLoading: false,
    data: [{ product_id: 7, product_type: "demo-product", manifest }],
  });
});

it("degrades to the fallback when a matching entry+slot resolve but no tenant is active", () => {
  mockUseActiveTenantId.mockReturnValue(undefined);

  render(<ExtensionPageRoute />);

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
});

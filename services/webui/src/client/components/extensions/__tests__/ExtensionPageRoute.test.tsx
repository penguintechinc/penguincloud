/**
 * `ExtensionPageRoute` — the generic route/nav proof for page-slot
 * extensions, with NO product name baked into the render decision: fixtures
 * below use an invented product type (`"demo-product"`) precisely so a
 * passing suite cannot be explained by a hidden per-product branch anywhere
 * in `ExtensionPageRoute.tsx`/`ExtensionSlotRenderer.tsx`/
 * `ExtensionRegistry.ts`.
 *
 * Mocks at the same boundary `ProductResourceRoute.test.tsx` establishes for
 * this kit (`stores/tenantStore`, `lib/api`) — `useConsoleManifests` runs
 * for real through `portal.get` down to the mocked `lib/api` instance, so
 * the manifests fetch itself is exercised, not stubbed away.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ExtensionPageRoute } from "../ExtensionPageRoute";
import {
  registerPageExtension,
  clearPageExtensions,
  type ExtensionPageProps,
} from "../ExtensionRegistry";
import { ExtensionFallback } from "../ExtensionFallback";
import type { ConsoleManifest, ExtensionSlot } from "../../kit/manifestTypes";

jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

const mockApiGet = jest.fn();
jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { get: (...args: unknown[]) => mockApiGet(...args) },
}));

function pageSlot(overrides: Partial<ExtensionSlot> = {}): ExtensionSlot {
  return {
    slot: "page",
    id: "demo-panel",
    label: "Demo Panel",
    resource: null,
    position: 0,
    ...overrides,
  };
}

function manifestFor(
  productType: string,
  extensions: ExtensionSlot[],
): ConsoleManifest {
  return {
    manifest_version: 2,
    product_type: productType,
    display_name: "Demo Product",
    nav: { items: [] },
    resources: [],
    operations: null,
    metrics: null,
    extensions,
  };
}

function renderRoute(): QueryClient {
  const queryClient = createAppQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <ExtensionPageRoute />
    </QueryClientProvider>,
  );
  return queryClient;
}

/** Same settle-before-assert discipline `ProductResourceRoute.test.tsx`
 * uses: the loading branch is a real render state distinct from the
 * fallback, so a bare `findByTestId` for the fallback could pass on the
 * loading frame without ever proving the routing decision. */
async function waitForManifestsSettled(
  queryClient: QueryClient,
): Promise<void> {
  await waitFor(() => {
    const query = queryClient
      .getQueryCache()
      .findAll()
      .find((q) => q.queryKey.includes("console-manifests"));
    expect(query?.state.status).not.toBe("pending");
  });
}

function DemoExtensionPage(props: ExtensionPageProps) {
  return (
    <div data-testid="demo-extension-page">
      {props.productType}:{props.productId}:{props.tenantId}:{props.slot.id}
    </div>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  clearPageExtensions();
  (useParams as jest.Mock).mockReturnValue({
    productType: "demo-product",
    extensionId: "demo-panel",
  });
});

afterEach(() => {
  clearPageExtensions();
});

it('registered: flag ON + a page slot registered as "{product}.{id}" renders the registered extension', async () => {
  registerPageExtension("demo-product", "demo-panel", () =>
    Promise.resolve({ default: DemoExtensionPage }),
  );
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo-product",
          manifest: manifestFor("demo-product", [pageSlot()]),
        },
      ],
      count: 1,
    },
  });

  renderRoute();

  expect(await screen.findByTestId("demo-extension-page")).toHaveTextContent(
    "demo-product:7:42:demo-panel",
  );
  expect(screen.queryByTestId("extension-fallback")).not.toBeInTheDocument();
});

it("unregistered: flag ON + a declared page slot with NO registry entry degrades to the generic fallback", async () => {
  // Deliberately no `registerPageExtension` call — this slot is declared by
  // the manifest but nothing is registered for "demo-product.demo-panel".
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo-product",
          manifest: manifestFor("demo-product", [pageSlot()]),
        },
      ],
      count: 1,
    },
  });

  const queryClient = renderRoute();
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
  expect(screen.queryByTestId("demo-extension-page")).not.toBeInTheDocument();
});

// Falsifiability check for the test above: if `ExtensionFallback` were
// removed/broken (e.g. renamed its `data-testid`, or `ExtensionSlotRenderer`
// stopped rendering it on an unresolved lookup), the assertion goes red
// rather than silently passing. Proven directly here rather than asserted
// only in prose: rendering the fallback in isolation with the SAME testid
// the test above depends on, so a change to either file that breaks the
// contract fails at least one of these two tests.
it("falsifiability: ExtensionFallback renders the exact testid the unregistered-slot assertion depends on", () => {
  render(<ExtensionFallback label="Demo Panel" />);

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
});

it("case: flag OFF (manifests endpoint 403s) degrades to the generic fallback, never a blank page", async () => {
  mockApiGet.mockRejectedValue(
    Object.assign(new Error("Forbidden"), {
      response: { status: 403, data: { error: "feature_disabled" } },
    }),
  );

  const queryClient = renderRoute();
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
});

it("case: a URL naming a slot the manifest no longer declares degrades to the fallback", async () => {
  (useParams as jest.Mock).mockReturnValue({
    productType: "demo-product",
    extensionId: "no-such-slot",
  });
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo-product",
          manifest: manifestFor("demo-product", [pageSlot()]),
        },
      ],
      count: 1,
    },
  });

  const queryClient = renderRoute();
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("extension-fallback")).toBeInTheDocument();
});

it("falls back with a generic label when the URL carries no extensionId param at all", async () => {
  (useParams as jest.Mock).mockReturnValue({
    productType: "demo-product",
    extensionId: undefined,
  });
  mockApiGet.mockResolvedValue({
    data: { manifests: [], count: 0 },
  });

  const queryClient = renderRoute();
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("extension-fallback")).toHaveTextContent(
    "extension is not available",
  );
});

it("shows a loading state before the manifests query settles, not the fallback", () => {
  mockApiGet.mockReturnValue(new Promise(() => {})); // never resolves

  renderRoute();

  expect(screen.getByTestId("extension-route-loading")).toBeInTheDocument();
  expect(screen.queryByTestId("extension-fallback")).not.toBeInTheDocument();
});

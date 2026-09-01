/**
 * `ProductResourceRoute` — the generic router-slot decision proven with NO
 * product name baked into the decision path: fixtures below use invented
 * product types (`"demo"`, `"brand-new-product"`) precisely so a passing
 * suite cannot be explained by a hidden per-product branch anywhere in
 * `ProductResourceRoute.tsx`/`manifestCapabilities.ts`.
 *
 * Mocks at the same boundary `ManifestResourceScreen.test.tsx` already
 * establishes for this kit (`lib/api`, `hooks/useProducts`,
 * `lib/featureGates`, `stores/tenantStore`, `api/resources/products`) —
 * `useConsoleManifests` runs for real through `portal.get` down to the
 * mocked `lib/api` instance, so the manifests fetch itself is exercised,
 * not stubbed away.
 *
 * Every test asserting a FALLBACK outcome first waits for the manifests
 * query to leave "pending" (`waitForManifestsSettled`) before checking the
 * DOM. Fallback is also this component's initial/loading render, so a
 * `findByTestId("fallback-marker")` alone would pass vacuously even if the
 * routing decision were broken and always routed — it would just catch the
 * loading frame on its way to a state the assertion never re-checks. Only
 * `case 2`'s deferred-promise variant proves this the hard way: an earlier
 * draft of this suite that used a bare `findByTestId` here stayed green
 * even with `SUPPORTED_CAPABILITIES` temporarily widened to cover
 * `'actions'` — the settle-then-assert pattern below is what catches that.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ProductResourceRoute } from "../ProductResourceRoute";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
  useProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

const mockProxyRequest = jest.fn();
jest.mock("../../../api/resources/products", () => ({
  proxyApi: { request: (...args: unknown[]) => mockProxyRequest(...args) },
}));

const mockApiGet = jest.fn();
jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { get: (...args: unknown[]) => mockApiGet(...args) },
}));

function FallbackScreen() {
  return <div data-testid="fallback-marker">Hand-written screen</div>;
}

function readOnlyResource(
  kind: string,
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
    kind,
    label: "Widget",
    plural_label: "Widgets",
    id_field: "id",
    name_field: "name",
    transport: "proxy",
    columns: [
      {
        field: "id",
        label: "ID",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
      },
    ],
    empty_state: "No widgets.",
    error_state: "Unable to load widgets.",
    list: {
      path_bytes: "/api/v1/widgets/",
      envelope: { keys: ["widgets"] },
      pagination: "none",
    },
    item_path: null,
    detail: { tabs: [] },
    actions: [],
    relationships: [],
    ...overrides,
  };
}

function manifestFor(
  productType: string,
  resource: ResourceDescriptor,
  operations: ConsoleManifest["operations"] = null,
): ConsoleManifest {
  return {
    manifest_version: 2,
    product_type: productType,
    display_name: "Demo Product",
    nav: { items: [{ kind: resource.kind, label: resource.plural_label }] },
    resources: [resource],
    operations,
    metrics: null,
    extensions: [],
  };
}

function renderRoute(productType: string, kind: string): QueryClient {
  const queryClient = createAppQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <ProductResourceRoute
        productType={productType}
        kind={kind}
        fallback={FallbackScreen}
      />
    </QueryClientProvider>,
  );
  return queryClient;
}

/**
 * Waits until the `console-manifests` query has left "pending" (succeeded
 * OR errored) before the caller inspects the DOM — see this file's module
 * doc for why a fallback assertion cannot skip this and still be
 * falsifiable.
 */
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

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
});

it("case 1: flag ON + a read-only manifest present routes through ManifestResourceScreen", async () => {
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "demo" }],
    isLoading: false,
  });
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo",
          manifest: manifestFor("demo", readOnlyResource("widgets")),
        },
      ],
      count: 1,
    },
  });
  mockProxyRequest.mockResolvedValue({ widgets: [] });

  renderRoute("demo", "widgets");

  expect(await screen.findByTestId("demo-screen")).toBeInTheDocument();
  expect(screen.queryByTestId("fallback-marker")).not.toBeInTheDocument();
});

it("case 2: flag ON + a manifest declaring actions falls back to the hand-written screen", async () => {
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "demo" }],
    isLoading: false,
  });
  const mutatingResource = readOnlyResource("widgets", {
    actions: [
      {
        verb: "restart",
        label: "Restart",
        variant: "primary",
        requires: "manage",
        confirm: "Restart?",
        starts_operations: false,
        form: null,
        enabled_when_field: null,
        enabled_when_in: [],
      },
    ],
  });
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo",
          manifest: manifestFor("demo", mutatingResource),
        },
      ],
      count: 1,
    },
  });

  const queryClient = renderRoute("demo", "widgets");
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("fallback-marker")).toBeInTheDocument();
  expect(screen.queryByTestId("demo-screen")).not.toBeInTheDocument();
  expect(mockProxyRequest).not.toHaveBeenCalled();
});

it("case 3: flag OFF (manifests endpoint 403s) falls back to the hand-written screen", async () => {
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "demo" }],
    isLoading: false,
  });
  mockApiGet.mockRejectedValue(
    Object.assign(new Error("Forbidden"), {
      response: { status: 403, data: { error: "feature_disabled" } },
    }),
  );

  const queryClient = renderRoute("demo", "widgets");
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("fallback-marker")).toBeInTheDocument();
  expect(screen.queryByTestId("demo-screen")).not.toBeInTheDocument();
});

it("case 4: a synthetic read-only product with NO hand-written screen still routes via the manifest — zero per-product code", async () => {
  mockConnections.mockReturnValue({
    data: [{ id: 99, product_type: "brand-new-product" }],
    isLoading: false,
  });
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 99,
          product_type: "brand-new-product",
          manifest: manifestFor("brand-new-product", readOnlyResource("items")),
        },
      ],
      count: 1,
    },
  });
  mockProxyRequest.mockResolvedValue({ widgets: [] });

  renderRoute("brand-new-product", "items");

  expect(
    await screen.findByTestId("brand-new-product-screen"),
  ).toBeInTheDocument();
  // The fallback prop is real (required by the component's own type), but
  // never rendered — nothing product-specific had to be written for this
  // product to onboard.
  expect(screen.queryByTestId("fallback-marker")).not.toBeInTheDocument();
});

it("falls back when the manifest has no matching resource kind at all", async () => {
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "demo" }],
    isLoading: false,
  });
  mockApiGet.mockResolvedValue({
    data: {
      manifests: [
        {
          product_id: 7,
          product_type: "demo",
          manifest: manifestFor("demo", readOnlyResource("widgets")),
        },
      ],
      count: 1,
    },
  });

  const queryClient = renderRoute("demo", "gizmos");
  await waitForManifestsSettled(queryClient);

  expect(screen.getByTestId("fallback-marker")).toBeInTheDocument();
});

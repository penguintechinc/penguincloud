/**
 * `useProductConnection` / `useProductResource` — the generic
 * tenant → connection → tenant-scoped-list-query chain every product's
 * resource hooks (`useGoughNodes`, `useNestDatabases`, ...) are built on.
 *
 * The `enabled` predicate is the point of most of this file: a query must
 * not fire before the tenant and the product's connection are both known,
 * because firing early is exactly the cross-tenant cache-key class this
 * repo already fixed once (see `api/keys.ts`).
 */

import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useProductConnection,
  useProductResource,
} from "../useProductResource";
import { queryKeys } from "../../../api/keys";

const mockUseProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
  useProductEnabled: (key: string) => mockUseProductEnabled(key),
}));

const mockUseProductConnections = jest.fn();
jest.mock("../../../hooks/useProducts", () => ({
  useProductConnections: (tenantId: number | undefined) =>
    mockUseProductConnections(tenantId),
}));

let currentTenant: { id: number } | null = { id: 42 };
jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant }),
}));

function client(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  currentTenant = { id: 42 };
  mockUseProductEnabled.mockReturnValue(true);
  mockUseProductConnections.mockReturnValue({
    data: [{ id: 7, product_type: "gough" }],
    isLoading: false,
  });
});

describe("useProductConnection", () => {
  it("resolves the connection matching productType and folds in the flag", () => {
    const { result } = renderHook(() => useProductConnection("gough"));

    expect(result.current).toEqual({
      tenantId: 42,
      productId: 7,
      isLoading: false,
      isEnabled: true,
    });
  });

  it("ignores a connection registered to a different product", () => {
    mockUseProductConnections.mockReturnValue({
      data: [{ id: 9, product_type: "nest" }],
      isLoading: false,
    });

    const { result } = renderHook(() => useProductConnection("gough"));

    expect(result.current.productId).toBeUndefined();
  });

  it("reports no tenant as undefined rather than inventing one", () => {
    currentTenant = null;

    const { result } = renderHook(() => useProductConnection("gough"));

    expect(result.current.tenantId).toBeUndefined();
  });
});

describe("useProductResource enabled predicate", () => {
  it("does not fire the query before a tenant is selected", async () => {
    currentTenant = null;
    mockUseProductConnections.mockReturnValue({
      data: undefined,
      isLoading: false,
    });
    const fetcher = jest.fn().mockResolvedValue([{ id: 1 }]);
    const qc = client();

    renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    // Give any accidental async fetch a chance to happen before asserting
    // it did not.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not fire the query while the connection list is still loading", async () => {
    mockUseProductConnections.mockReturnValue({
      data: undefined,
      isLoading: true,
    });
    const fetcher = jest.fn().mockResolvedValue([{ id: 1 }]);
    const qc = client();

    renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not fire the query when the feature flag is off, even with a resolved connection", async () => {
    mockUseProductEnabled.mockReturnValue(false);
    const fetcher = jest.fn().mockResolvedValue([{ id: 1 }]);
    const qc = client();

    renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("fires only once tenant, connection and flag are all known", async () => {
    const fetcher = jest.fn().mockResolvedValue([{ id: 1, name: "rack-a" }]);
    const qc = client();

    const { result } = renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(7));
    await waitFor(() =>
      expect(result.current.data).toEqual([{ id: 1, name: "rack-a" }]),
    );
    expect(result.current.productId).toBe(7);
    expect(result.current.tenantId).toBe(42);
  });

  it("caches under queryKeyPrefix + tenantId + productId + kind, exactly matching the product-specific key factory", async () => {
    const fetcher = jest.fn().mockResolvedValue([]);
    const qc = client();

    renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    const expectedKey = queryKeys.goughResource(42, 7, "nodes");
    expect(qc.getQueryData(expectedKey)).toEqual([]);
  });

  it("passes fetched rows through untouched — no coercion of falsy-but-present values", async () => {
    // A missing summary rendering as 0.00, or a null scope_id rendering as a
    // dash instead of "Everyone", both trace back to a layer that normalised
    // an absent value on the way through. This hook must not be that layer.
    const rows = [{ id: 1, total: 0, scope_id: null, note: "" }];
    const fetcher = jest.fn().mockResolvedValue(rows);
    const qc = client();

    const { result } = renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(result.current.data).toEqual(rows));
  });

  it("surfaces a query error rather than resolving to an empty list", async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error("boom"));
    const qc = client();

    const { result } = renderHook(
      () =>
        useProductResource({
          productType: "gough",
          kind: "nodes",
          queryKeyPrefix: queryKeys.gough(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.data).toBeUndefined();
  });
});

// Confirms the gating is not an accident of this test's mock shape: swapping
// productType must swap which flag and which connection are consulted.
describe("generic over product", () => {
  it("keys the flag check and the connection match off productType", async () => {
    mockUseProductConnections.mockReturnValue({
      data: [{ id: 3, product_type: "nest" }],
      isLoading: false,
    });
    const fetcher = jest.fn().mockResolvedValue([{ id: 1 }]);
    const qc = client();

    const { result } = renderHook(
      () =>
        useProductResource({
          productType: "nest",
          kind: "databases",
          queryKeyPrefix: queryKeys.nest(),
          fetcher,
        }),
      { wrapper: wrapper(qc) },
    );

    expect(mockUseProductEnabled).toHaveBeenCalledWith("nest");
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(3));
    expect(result.current.productId).toBe(3);
  });
});

/**
 * `useConsoleManifests` — the tenant-scoped fetch of
 * `GET /api/v1/console/manifests`.
 *
 * Mocks the shared axios instance (`lib/api`), the same layer
 * `api/__tests__/portal.test.ts` mocks at — `portal.get` is exercised for
 * real, only the network boundary is a double.
 */
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useConsoleManifests } from "../useConsoleManifests";
import api from "../../../lib/api";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

let currentTenant: { id: number } | null = { id: 42 };
jest.mock("../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant }),
}));

const mockedApi = api as unknown as { get: jest.Mock };

function client(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  currentTenant = { id: 42 };
});

it("fetches manifests scoped to the active tenant", async () => {
  mockedApi.get.mockResolvedValue({
    data: {
      manifests: [
        { product_id: 7, product_type: "gough", manifest: { resources: [] } },
      ],
      count: 1,
    },
  });

  const qc = client();
  const { result } = renderHook(() => useConsoleManifests(), {
    wrapper: wrapper(qc),
  });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));

  expect(result.current.data).toHaveLength(1);
  expect(result.current.data?.[0].product_type).toBe("gough");
  expect(mockedApi.get).toHaveBeenCalledWith(
    "/console/manifests",
    expect.objectContaining({ params: { tenant_id: 42 } }),
  );
});

it("stays disabled — and fires no request — before a tenant is selected", () => {
  currentTenant = null;

  const qc = client();
  const { result } = renderHook(() => useConsoleManifests(), {
    wrapper: wrapper(qc),
  });

  expect(result.current.fetchStatus).toBe("idle");
  expect(mockedApi.get).not.toHaveBeenCalled();
});

it("keys the query by tenant, so switching tenants cannot serve stale cross-tenant rows", async () => {
  mockedApi.get.mockResolvedValue({ data: { manifests: [], count: 0 } });
  const qc = client();

  const first = renderHook(() => useConsoleManifests(), {
    wrapper: wrapper(qc),
  });
  await waitFor(() => expect(first.result.current.isSuccess).toBe(true));

  currentTenant = { id: 99 };
  const second = renderHook(() => useConsoleManifests(), {
    wrapper: wrapper(qc),
  });
  await waitFor(() => expect(second.result.current.isSuccess).toBe(true));

  expect(mockedApi.get).toHaveBeenCalledTimes(2);
  expect(mockedApi.get).toHaveBeenNthCalledWith(
    2,
    "/console/manifests",
    expect.objectContaining({ params: { tenant_id: 99 } }),
  );
});

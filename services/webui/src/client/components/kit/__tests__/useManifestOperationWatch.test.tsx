/**
 * `useManifestOperationWatch` — the product-agnostic, response-driven
 * operation watch for a `mode="watch"` manifest resource. Generalises
 * `pages/products/nest/useNestOperations.ts`'s `useNestOperationWatch` off a
 * caller-supplied `kind` instead of Nest's own hardcoded
 * `NEST_OPERATION_KIND`.
 */
import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  nextOperationPollInterval,
  useManifestOperationWatch,
} from "../useManifestOperationWatch";
import api from "../../../lib/api";
import { queryKeys } from "../../../api/keys";
import type { OperationLike } from "../operationsPanelTypes";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedApi = api as unknown as { get: jest.Mock };

// Long enough that no real automatic refetch fires mid-test — every
// terminal-state transition below is driven explicitly via `qc.refetchQueries`,
// never by waiting out this interval.
const POLL_MS = 60_000;

function client(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function op(overrides: Partial<OperationLike> = {}): OperationLike {
  return {
    id: "op-1",
    kind: "database",
    state: "running",
    status: "provisioning",
    is_terminal: false,
    ...overrides,
  };
}

function resourceListKey(productType: string, kind: string) {
  return {
    queryKey: [...queryKeys.consoleManifestResource(productType), 42, 7, kind],
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("nextOperationPollInterval", () => {
  it("keeps polling while there is no data yet", () => {
    expect(nextOperationPollInterval(undefined, POLL_MS)).toBe(POLL_MS);
  });

  it("keeps polling a not-yet-terminal operation", () => {
    expect(nextOperationPollInterval(op({ is_terminal: false }), POLL_MS)).toBe(
      POLL_MS,
    );
  });

  it("stops polling a terminal operation", () => {
    expect(nextOperationPollInterval(op({ is_terminal: true }), POLL_MS)).toBe(
      false,
    );
  });
});

describe("useManifestOperationWatch", () => {
  it("does nothing on an empty watch() call", () => {
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () => useManifestOperationWatch("nest", 42, 7, "database", true, POLL_MS),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch([]));

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(mockedApi.get).not.toHaveBeenCalled();
    expect(result.current.operations).toHaveLength(0);
  });

  it("polls a watched id at the generic typed operation route and invalidates the resource list immediately", async () => {
    mockedApi.get.mockResolvedValue({ data: op({ is_terminal: false }) });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () => useManifestOperationWatch("nest", 42, 7, "database", true, POLL_MS),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));

    expect(invalidateSpy).toHaveBeenCalledWith(
      resourceListKey("nest", "database"),
    );
    await waitFor(() => expect(result.current.operations).toHaveLength(1));
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/products/7/operations/database/op-1",
    );
    expect(result.current.isPolling).toBe(true);
  });

  it("does not register a watched id twice — the second watch() call only adds the new id", async () => {
    mockedApi.get.mockImplementation(async (url: string) => {
      if (url.endsWith("/op-1")) return { data: op({ id: "op-1" }) };
      if (url.endsWith("/op-2"))
        return { data: op({ id: "op-2", kind: "database" }) };
      throw new Error(`unexpected url ${url}`);
    });
    const qc = client();
    const { result } = renderHook(
      () => useManifestOperationWatch("nest", 42, 7, "database", true, POLL_MS),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));
    await waitFor(() => expect(result.current.operations).toHaveLength(1));

    act(() => result.current.watch(["op-1", "op-2"]));
    await waitFor(() => expect(result.current.operations).toHaveLength(2));

    // Had the already-watched "op-1" been re-appended instead of filtered,
    // this would read 3, with "op-1" duplicated.
    expect(
      result.current.operations.map((operation) => operation.id).sort(),
    ).toEqual(["op-1", "op-2"]);
  });

  it("keeps polling while not terminal, stops and settle-invalidates once terminal — falsifiability", async () => {
    mockedApi.get.mockResolvedValue({ data: op({ is_terminal: false }) });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () => useManifestOperationWatch("nest", 42, 7, "database", true, POLL_MS),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));
    await waitFor(() => expect(result.current.operations).toHaveLength(1));
    expect(result.current.isPolling).toBe(true);
    // Only the immediate "just started" invalidate so far.
    expect(invalidateSpy).toHaveBeenCalledTimes(1);

    // Not-yet-terminal: refetching again must not settle-invalidate.
    await act(async () => {
      await qc.refetchQueries({
        queryKey: queryKeys.consoleManifestOperationWatch(42, 7, "op-1"),
      });
    });
    expect(result.current.isPolling).toBe(true);
    expect(invalidateSpy).toHaveBeenCalledTimes(1);

    // Now the product reports it finished.
    mockedApi.get.mockResolvedValue({ data: op({ is_terminal: true }) });
    await act(async () => {
      await qc.refetchQueries({
        queryKey: queryKeys.consoleManifestOperationWatch(42, 7, "op-1"),
      });
    });

    await waitFor(() => expect(result.current.isPolling).toBe(false));
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenNthCalledWith(
      2,
      resourceListKey("nest", "database"),
    );

    // Settling is a one-time transition per operation: a further refetch of
    // the still-terminal operation must not invalidate a third time.
    await act(async () => {
      await qc.refetchQueries({
        queryKey: queryKeys.consoleManifestOperationWatch(42, 7, "op-1"),
      });
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });

  it("never fires while disabled, even after watch()", () => {
    const qc = client();
    const { result } = renderHook(
      () =>
        useManifestOperationWatch("nest", 42, 7, "database", false, POLL_MS),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));

    expect(mockedApi.get).not.toHaveBeenCalled();
  });

  it("addresses the watch URL with operation_kind when the manifest declares one, while resource-list invalidation still uses the resource's own kind", async () => {
    mockedApi.get.mockResolvedValue({ data: op({ is_terminal: false }) });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () =>
        useManifestOperationWatch(
          "nest",
          42,
          7,
          "database",
          true,
          POLL_MS,
          "operation",
        ),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));

    // Resource-list invalidation is keyed off the RESOURCE's kind
    // ("database"), never the operation kind — `useProductResource.ts`'s
    // list query is keyed the same way.
    expect(invalidateSpy).toHaveBeenCalledWith(
      resourceListKey("nest", "database"),
    );
    await waitFor(() => expect(result.current.operations).toHaveLength(1));
    // The watch URL itself addresses "operation", not "database" — Nest's
    // `get_operation` 501s on anything else.
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/products/7/operations/operation/op-1",
    );
  });

  it("falls back to the resource's own kind for the watch URL when operation_kind is null", async () => {
    mockedApi.get.mockResolvedValue({ data: op({ is_terminal: false }) });
    const qc = client();
    const { result } = renderHook(
      () =>
        useManifestOperationWatch(
          "nest",
          42,
          7,
          "database",
          true,
          POLL_MS,
          null,
        ),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));

    await waitFor(() => expect(result.current.operations).toHaveLength(1));
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/products/7/operations/database/op-1",
    );
  });

  it("never fires before a product id is known", () => {
    const qc = client();
    const { result } = renderHook(
      () =>
        useManifestOperationWatch(
          "nest",
          42,
          undefined,
          "database",
          true,
          POLL_MS,
        ),
      { wrapper: wrapper(qc) },
    );

    act(() => result.current.watch(["op-1"]));

    expect(mockedApi.get).not.toHaveBeenCalled();
  });
});

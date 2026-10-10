/**
 * `useManifestOperations` — the product-agnostic operations poll, built on
 * the SAME typed portal route every hand-written product operations hook
 * (`useGoughOperations`) already uses.
 */
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  nextPollInterval,
  useCancelManifestOperation,
  useManifestOperationLogs,
  useManifestOperations,
} from "../useManifestOperations";
import api from "../../../lib/api";
import type { OperationLike } from "../operationsPanelTypes";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

const mockedApi = api as unknown as { get: jest.Mock; post: jest.Mock };

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
});

it("fetches through the generic typed operations route for the given product", async () => {
  mockedApi.get.mockResolvedValue({
    data: {
      operations: [
        { id: "op-1", kind: "deploy", state: "running", is_terminal: false },
      ],
    },
  });

  const qc = client();
  const { result } = renderHook(
    () => useManifestOperations(42, 7, true, 5000),
    {
      wrapper: wrapper(qc),
    },
  );

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toHaveLength(1);
  expect(mockedApi.get).toHaveBeenCalledWith("/products/7/operations");
});

it("does not fire while disabled (no operations declared on the manifest)", () => {
  const qc = client();
  const { result } = renderHook(
    () => useManifestOperations(42, 7, false, 5000),
    {
      wrapper: wrapper(qc),
    },
  );

  expect(result.current.fetchStatus).toBe("idle");
  expect(mockedApi.get).not.toHaveBeenCalled();
});

it("does not fire before a product id is known", () => {
  const qc = client();
  const { result } = renderHook(
    () => useManifestOperations(42, undefined, true, 5000),
    {
      wrapper: wrapper(qc),
    },
  );

  expect(result.current.fetchStatus).toBe("idle");
  expect(mockedApi.get).not.toHaveBeenCalled();
});

function op(overrides: Partial<OperationLike>): OperationLike {
  return {
    id: "op-1",
    kind: "deploy",
    state: "running",
    status: "running",
    is_terminal: false,
    ...overrides,
  };
}

describe("nextPollInterval", () => {
  it("stops when there is no data yet", () => {
    expect(nextPollInterval(undefined, 5000)).toBe(false);
  });

  it("stops when the list is empty", () => {
    expect(nextPollInterval([], 5000)).toBe(false);
  });

  it("polls while any operation is non-terminal", () => {
    expect(
      nextPollInterval(
        [op({ is_terminal: true }), op({ is_terminal: false })],
        5000,
      ),
    ).toBe(5000);
  });

  it("stops once every operation is terminal", () => {
    expect(
      nextPollInterval(
        [op({ is_terminal: true }), op({ is_terminal: true })],
        5000,
      ),
    ).toBe(false);
  });
});

describe("useCancelManifestOperation", () => {
  it("posts to the generic typed cancel route and invalidates the operations query", async () => {
    mockedApi.post.mockResolvedValue({ data: {} });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCancelManifestOperation(42, 7), {
      wrapper: wrapper(qc),
    });

    result.current.mutate({ kind: "deployment", operationId: "op-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/cancel",
    );
    expect(invalidateSpy).toHaveBeenCalled();
  });

  it("refuses to fire without a resolved product id", async () => {
    const qc = client();
    const { result } = renderHook(
      () => useCancelManifestOperation(42, undefined),
      {
        wrapper: wrapper(qc),
      },
    );

    result.current.mutate({ kind: "deployment", operationId: "op-1" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedApi.post).not.toHaveBeenCalled();
  });
});

describe("useManifestOperationLogs", () => {
  it("fetches through the generic typed logs route when enabled", async () => {
    mockedApi.get.mockResolvedValue({
      data: { logs: [{ message: "started" }] },
    });
    const qc = client();
    const { result } = renderHook(
      () =>
        useManifestOperationLogs(42, 7, "deployment", "op-1", {
          enabled: true,
          isTerminal: false,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ message: "started" }]);
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/products/7/operations/deployment/op-1/logs",
    );
  });

  it("does not fire until enabled — an operator has not opened the disclosure yet", () => {
    const qc = client();
    const { result } = renderHook(
      () =>
        useManifestOperationLogs(42, 7, "deployment", "op-1", {
          enabled: false,
          isTerminal: false,
        }),
      { wrapper: wrapper(qc) },
    );

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockedApi.get).not.toHaveBeenCalled();
  });
});

/**
 * `useCreateManifestResource`/`useDeleteManifestResource`/
 * `usePerformManifestAction` — the generic typed-route mutations
 * (`app/resources_api.py`, `operations_api.py`'s `perform_resource_action`)
 * a manifest-driven screen dispatches through, never the byte proxy.
 */
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useCreateManifestResource,
  useDeleteManifestResource,
  usePerformManifestAction,
  useUpdateManifestResource,
  startedManifestOperationIds,
} from "../manifestMutations";
import api from "../../../lib/api";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { post: jest.fn(), delete: jest.fn(), put: jest.fn() },
}));

const mockedApi = api as unknown as {
  post: jest.Mock;
  delete: jest.Mock;
  put: jest.Mock;
};

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

describe("useCreateManifestResource", () => {
  it("posts to the generic typed create route", async () => {
    mockedApi.post.mockResolvedValue({ data: { id: "9" } });
    const qc = client();
    const { result } = renderHook(
      () => useCreateManifestResource("gough", 42, 7, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ name: "web" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/resources/biomes",
      { name: "web" },
    );
  });

  it("refuses to fire without a resolved product id", async () => {
    const qc = client();
    const { result } = renderHook(
      () => useCreateManifestResource("gough", 42, undefined, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ name: "web" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedApi.post).not.toHaveBeenCalled();
  });

  it("invalidates the resource list and operations queries on success", async () => {
    mockedApi.post.mockResolvedValue({ data: {} });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () => useCreateManifestResource("gough", 42, 7, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ name: "web" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});

describe("useDeleteManifestResource", () => {
  it("deletes at the generic typed item route", async () => {
    mockedApi.delete.mockResolvedValue({ data: { deleted: true } });
    const qc = client();
    const { result } = renderHook(
      () => useDeleteManifestResource("gough", 42, 7, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate("4");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.delete).toHaveBeenCalledWith(
      "/products/7/resources/biomes/4",
    );
  });

  it("refuses to fire without a resolved product id", async () => {
    const qc = client();
    const { result } = renderHook(
      () => useDeleteManifestResource("gough", 42, undefined, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate("4");

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedApi.delete).not.toHaveBeenCalled();
  });
});

describe("useUpdateManifestResource", () => {
  it("PUTs to the same generic typed item route useDeleteManifestResource uses", async () => {
    mockedApi.put.mockResolvedValue({ data: { id: "4" } });
    const qc = client();
    const { result } = renderHook(
      () => useUpdateManifestResource("gough", 42, 7, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ resourceId: "4", payload: { name: "web-2" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.put).toHaveBeenCalledWith(
      "/products/7/resources/biomes/4",
      { name: "web-2" },
    );
  });

  it("refuses to fire without a resolved product id", async () => {
    const qc = client();
    const { result } = renderHook(
      () => useUpdateManifestResource("gough", 42, undefined, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ resourceId: "4", payload: { name: "web-2" } });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedApi.put).not.toHaveBeenCalled();
  });

  it("invalidates the resource list and operations queries on success", async () => {
    mockedApi.put.mockResolvedValue({ data: {} });
    const qc = client();
    const invalidateSpy = jest.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(
      () => useUpdateManifestResource("gough", 42, 7, "biomes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ resourceId: "4", payload: { name: "web-2" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});

describe("usePerformManifestAction", () => {
  it("posts the verb to the generic typed action route", async () => {
    mockedApi.post.mockResolvedValue({ data: { accepted: true } });
    const qc = client();
    const { result } = renderHook(
      () => usePerformManifestAction("gough", 42, 7, "nodes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ resourceId: "12", verb: "evacuate" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12/actions/evacuate",
      {},
    );
  });

  it("forwards an optional payload verbatim", async () => {
    mockedApi.post.mockResolvedValue({ data: {} });
    const qc = client();
    const { result } = renderHook(
      () => usePerformManifestAction("gough", 42, 7, "nodes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({
      resourceId: "12",
      verb: "deploy",
      payload: { biome_id: 4 },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/resources/nodes/12/actions/deploy",
      { biome_id: 4 },
    );
  });

  it("refuses to fire without a resolved product id", async () => {
    const qc = client();
    const { result } = renderHook(
      () => usePerformManifestAction("gough", 42, undefined, "nodes"),
      { wrapper: wrapper(qc) },
    );

    result.current.mutate({ resourceId: "12", verb: "evacuate" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedApi.post).not.toHaveBeenCalled();
  });
});

describe("startedManifestOperationIds", () => {
  it("collects every id from an action's operations[]", () => {
    expect(
      startedManifestOperationIds({
        operations: [{ id: "op-1" }, { id: "op-2" }],
      }),
    ).toEqual(["op-1", "op-2"]);
  });

  it("reads a create's single operation_id as a one-element list", () => {
    expect(startedManifestOperationIds({ operation_id: "op-9" })).toEqual([
      "op-9",
    ]);
  });

  it("returns an empty list for a create that finished synchronously (operation_id null)", () => {
    expect(startedManifestOperationIds({ operation_id: null })).toEqual([]);
  });

  it("returns an empty list for a create with operation_id absent entirely", () => {
    expect(startedManifestOperationIds({})).toEqual([]);
  });

  it("returns an empty list for an action that completed synchronously (operations: [])", () => {
    expect(startedManifestOperationIds({ operations: [] })).toEqual([]);
  });

  it("falls through to the operation_id check when operations is present but undefined", () => {
    expect(startedManifestOperationIds({ operations: undefined })).toEqual([]);
  });
});

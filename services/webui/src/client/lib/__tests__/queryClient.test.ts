/**
 * `createAppQueryClient` is the shared mutation path Defect 1 asked for: one
 * `MutationCache.onError`, wired once, that every mutation in the app goes
 * through — instead of three copies (Gough, Nest, Tobogganing), none of
 * which had it. These tests exercise that wiring directly, independent of
 * any product screen, so the guarantee is provable without going through a
 * form.
 *
 * Every rejecting case below chains `.catch(() => undefined)`:
 * `Mutation#execute` re-throws after every callback runs (so `mutateAsync`
 * can reject), and by then the cache's own `onError` — the thing being
 * tested — has already fired. The assertions read the store, not this
 * promise.
 */
import { useMutationErrorStore } from "../../stores/mutationErrorStore";
import { GENERIC_MUTATION_ERROR_MESSAGE } from "../mutationError";
import { createAppQueryClient } from "../queryClient";

beforeEach(() => {
  useMutationErrorStore.setState({ errors: [] });
});

describe("createAppQueryClient", () => {
  it("reports a rejected mutation to the shared error store", async () => {
    const client = createAppQueryClient();

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: () =>
          Promise.reject({
            isAxiosError: true,
            response: { data: { error: "Route not allowed" } },
          }),
      })
      .execute(undefined)
      .catch(() => undefined);

    expect(useMutationErrorStore.getState().errors).toEqual([
      expect.objectContaining({ message: "Route not allowed" }),
    ]);
  });

  it("reports every mutation independently — one entry does not replace another", async () => {
    const client = createAppQueryClient();
    const cache = client.getMutationCache();

    await cache
      .build(client, {
        mutationFn: () => Promise.reject(new Error("first failure")),
      })
      .execute(undefined)
      .catch(() => undefined);
    await cache
      .build(client, {
        mutationFn: () => Promise.reject(new Error("second failure")),
      })
      .execute(undefined)
      .catch(() => undefined);

    const messages = useMutationErrorStore
      .getState()
      .errors.map((e) => e.message);
    expect(messages).toEqual(["first failure", "second failure"]);
  });

  it("does not report a mutation that succeeds", async () => {
    const client = createAppQueryClient();

    await client
      .getMutationCache()
      .build(client, { mutationFn: () => Promise.resolve("ok") })
      .execute(undefined);

    expect(useMutationErrorStore.getState().errors).toEqual([]);
  });

  it("still runs the global handler when the mutation defines its own onError", async () => {
    // The property the fix depends on: a product hook (or an inline
    // `.mutate(vars, { onError })`) does not opt the mutation out of the
    // shared banner just by handling the rejection itself.
    const client = createAppQueryClient();
    const localOnError = jest.fn();

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: () => Promise.reject(new Error("still reported")),
        onError: localOnError,
      })
      .execute(undefined)
      .catch(() => undefined);

    expect(localOnError).toHaveBeenCalled();
    expect(useMutationErrorStore.getState().errors).toEqual([
      expect.objectContaining({ message: "still reported" }),
    ]);
  });

  it("falls back to the generic message rather than the raw error object", async () => {
    const client = createAppQueryClient();

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: () =>
          Promise.reject({ isAxiosError: true, response: { data: {} } }),
      })
      .execute(undefined)
      .catch(() => undefined);

    expect(useMutationErrorStore.getState().errors).toEqual([
      expect.objectContaining({ message: GENERIC_MUTATION_ERROR_MESSAGE }),
    ]);
  });
});

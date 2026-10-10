/**
 * `mutationErrorStore` unit tests — the cap, dedupe and clearAll behaviour
 * I3 in the mutation-error-surfacing review asked for, exercised directly
 * against the store rather than through a mutation or the banner.
 */
import { useMutationErrorStore } from "../mutationErrorStore";

beforeEach(() => {
  useMutationErrorStore.setState({ errors: [] });
});

describe("mutationErrorStore", () => {
  it("starts empty", () => {
    expect(useMutationErrorStore.getState().errors).toEqual([]);
  });

  it("queues a reported message", () => {
    useMutationErrorStore.getState().report("Route not allowed");

    expect(useMutationErrorStore.getState().errors).toEqual([
      expect.objectContaining({ message: "Route not allowed" }),
    ]);
  });

  it("queues distinct messages independently", () => {
    useMutationErrorStore.getState().report("first failure");
    useMutationErrorStore.getState().report("second failure");

    const messages = useMutationErrorStore
      .getState()
      .errors.map((e) => e.message);
    expect(messages).toEqual(["first failure", "second failure"]);
  });

  it("dedupes an identical message instead of stacking a duplicate", () => {
    // Three Save clicks on the same still-broken form used to produce three
    // identical banners.
    useMutationErrorStore.getState().report("Route not allowed");
    useMutationErrorStore.getState().report("Route not allowed");
    useMutationErrorStore.getState().report("Route not allowed");

    expect(useMutationErrorStore.getState().errors).toHaveLength(1);
  });

  it("bumps a duplicate to the end of the queue rather than leaving it stale", () => {
    useMutationErrorStore.getState().report("first failure");
    useMutationErrorStore.getState().report("Route not allowed");
    useMutationErrorStore.getState().report("first failure");

    const messages = useMutationErrorStore
      .getState()
      .errors.map((e) => e.message);
    expect(messages).toEqual(["Route not allowed", "first failure"]);
  });

  it("caps the queue rather than growing without bound", () => {
    for (let i = 0; i < 8; i += 1) {
      useMutationErrorStore.getState().report(`failure ${i}`);
    }

    const state = useMutationErrorStore.getState();
    expect(state.errors.length).toBeLessThanOrEqual(5);
    // The oldest entries are dropped — the most recent failures are the
    // ones still worth an operator's attention.
    const messages = state.errors.map((e) => e.message);
    expect(messages).toEqual([
      "failure 3",
      "failure 4",
      "failure 5",
      "failure 6",
      "failure 7",
    ]);
  });

  it("dismisses one entry without clearing the others", () => {
    useMutationErrorStore.getState().report("keep me");
    useMutationErrorStore.getState().report("dismiss me");
    const [, target] = useMutationErrorStore.getState().errors;

    useMutationErrorStore.getState().dismiss(target!.id);

    const messages = useMutationErrorStore
      .getState()
      .errors.map((e) => e.message);
    expect(messages).toEqual(["keep me"]);
  });

  it("clearAll empties the queue regardless of how many are pending", () => {
    useMutationErrorStore.getState().report("first failure");
    useMutationErrorStore.getState().report("second failure");

    useMutationErrorStore.getState().clearAll();

    expect(useMutationErrorStore.getState().errors).toEqual([]);
  });
});

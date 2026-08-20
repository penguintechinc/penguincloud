/**
 * Route-change clearing for queued mutation errors (I3).
 *
 * Without this, a failure raised on one screen stayed queued for the rest
 * of the session regardless of where the operator navigated next — a Gough
 * failure was still pinned while they worked in Nest.
 */
import { renderHook } from "@testing-library/react";
import { useLocation } from "react-router";
import { useClearMutationErrorsOnNavigate } from "../useClearMutationErrorsOnNavigate";
import { useMutationErrorStore } from "../../stores/mutationErrorStore";

const mockUseLocation = useLocation as jest.Mock;

function setPath(pathname: string) {
  mockUseLocation.mockReturnValue({ pathname });
}

beforeEach(() => {
  jest.clearAllMocks();
  useMutationErrorStore.setState({ errors: [] });
});

describe("useClearMutationErrorsOnNavigate", () => {
  it("clears queued errors when the route changes", () => {
    setPath("/products/gough/biomes");
    useMutationErrorStore.setState({
      errors: [{ id: 1, message: "Insufficient permissions" }],
    });

    const { rerender } = renderHook(() => useClearMutationErrorsOnNavigate());
    // Mount alone does not assert anything new here (see the next test);
    // this test is about what happens on the SECOND render, after the path
    // actually changes.
    expect(useMutationErrorStore.getState().errors).toEqual([]);

    // Re-seed to prove the clear on navigation, not the mount-time clear.
    useMutationErrorStore.setState({
      errors: [{ id: 2, message: "Route not allowed" }],
    });
    setPath("/products/nest/databases");
    rerender();

    expect(useMutationErrorStore.getState().errors).toEqual([]);
  });

  it("clears on mount, since an error from a prior screen should not survive arriving at a new one", () => {
    setPath("/products/gough/biomes");
    useMutationErrorStore.setState({
      errors: [{ id: 1, message: "stale from a previous screen" }],
    });

    renderHook(() => useClearMutationErrorsOnNavigate());

    expect(useMutationErrorStore.getState().errors).toEqual([]);
  });

  it("does not clear on a re-render with the same pathname", () => {
    setPath("/products/gough/biomes");
    const { rerender } = renderHook(() => useClearMutationErrorsOnNavigate());

    useMutationErrorStore.setState({
      errors: [{ id: 1, message: "still relevant on this screen" }],
    });
    rerender();

    expect(useMutationErrorStore.getState().errors).toHaveLength(1);
  });
});

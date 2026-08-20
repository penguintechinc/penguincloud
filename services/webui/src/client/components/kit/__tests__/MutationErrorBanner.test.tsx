/**
 * `MutationErrorBanner` reads `mutationErrorStore` directly — the store, not
 * a rendered mutation, is what this component contracts with. Wiring it to a
 * real mutation is covered end-to-end in each product's page tests
 * (SwgPolicyPage, GoughScreens, DatabasesPage) and in `lib/queryClient.test.ts`.
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MutationErrorBanner from "../MutationErrorBanner";
import { useMutationErrorStore } from "../../../stores/mutationErrorStore";

beforeEach(() => {
  useMutationErrorStore.setState({ errors: [] });
});

describe("MutationErrorBanner", () => {
  it("renders nothing when there are no errors", () => {
    render(<MutationErrorBanner />);
    expect(screen.queryByTestId("mutation-error-banner")).toBeNull();
  });

  it("announces a reported error as an alert", () => {
    useMutationErrorStore.setState({
      errors: [{ id: 1, message: "Route not allowed" }],
    });
    render(<MutationErrorBanner />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Route not allowed");
    expect(alert).toHaveAttribute("aria-live", "assertive");
  });

  it("renders more than one queued error at once", () => {
    useMutationErrorStore.setState({
      errors: [
        { id: 1, message: "first failure" },
        { id: 2, message: "second failure" },
      ],
    });
    render(<MutationErrorBanner />);

    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(screen.getByText("first failure")).toBeInTheDocument();
    expect(screen.getByText("second failure")).toBeInTheDocument();
  });

  it("updates live as report() queues a new entry after mount", () => {
    // Distinct from the two tests above (pre-seeded state): this is the
    // shape the real usage takes — mounted once in Layout, before any
    // mutation has failed yet.
    render(<MutationErrorBanner />);
    expect(screen.queryByRole("alert")).toBeNull();

    act(() => {
      useMutationErrorStore.getState().report("Route not allowed");
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Route not allowed");
  });

  it("dismisses one entry via its close button without clearing the others", async () => {
    const user = userEvent.setup();
    useMutationErrorStore.setState({
      errors: [
        { id: 1, message: "keep me" },
        { id: 2, message: "dismiss me" },
      ],
    });
    render(<MutationErrorBanner />);

    const dismissButtons = screen.getAllByLabelText("Dismiss error");
    await user.click(dismissButtons[1]);

    expect(screen.getByText("keep me")).toBeInTheDocument();
    expect(screen.queryByText("dismiss me")).toBeNull();
  });

  it("is keyboard-reachable: Enter on a focused dismiss button dismisses it", async () => {
    const user = userEvent.setup();
    useMutationErrorStore.setState({
      errors: [{ id: 1, message: "close me with the keyboard" }],
    });
    render(<MutationErrorBanner />);

    screen.getByLabelText("Dismiss error").focus();
    await user.keyboard("{Enter}");

    expect(screen.queryByText("close me with the keyboard")).toBeNull();
  });
});

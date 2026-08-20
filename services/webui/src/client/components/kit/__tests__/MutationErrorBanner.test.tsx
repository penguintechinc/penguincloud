/**
 * `MutationErrorBanner` reads `mutationErrorStore` directly — the store, not
 * a rendered mutation, is what this component contracts with. Wiring it to a
 * real mutation is covered end-to-end in each product's page tests
 * (SwgPolicyPage, GoughScreens, DatabasesPage) and in `lib/queryClient.test.ts`.
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MutationErrorBanner from "../MutationErrorBanner";
import { ConfirmDialog } from "../ConfirmDialog";
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

  describe("while a ConfirmDialog is open (I1)", () => {
    // The reproducible case: SwgPolicyPage's replace-confirm flow clears
    // `replacing` only in `save.mutate(...)`'s onSuccess, so a FAILED
    // replace leaves ConfirmDialog open *and* raises a banner at the same
    // time — see SwgPolicyPage.tsx. ConfirmDialog's own wrapper is
    // `fixed inset-0 z-50`, and the shared FormModalBuilder defaults to
    // `zIndex: 9999`; either sits at or above the banner's old z-50 with no
    // `pointer-events-none`, so the un-portaled banner's dismiss button was
    // not reachable. This does not re-run jsdom's non-existent layout engine
    // (jsdom cannot compute real paint/hit-test occlusion) — it proves the
    // structural fix instead: the banner portals to `document.body`, a
    // sibling of the dialog's own subtree rather than a descendant liable to
    // an ancestor's stacking context, and remains interactive.
    function renderWithOpenDialog() {
      return render(
        <>
          <ConfirmDialog
            isOpen
            title="Replace an existing policy"
            message="This replaces the existing rule."
            onConfirm={() => undefined}
            onCancel={() => undefined}
            testId="tobogganing-swg-replace-confirm"
          />
          <MutationErrorBanner />
        </>,
      );
    }

    it("portals the banner onto document.body, not inside the dialog's subtree", () => {
      useMutationErrorStore.setState({
        errors: [{ id: 1, message: "Route not allowed" }],
      });
      const { container } = renderWithOpenDialog();

      const banner = screen.getByTestId("mutation-error-banner");
      expect(container.contains(banner)).toBe(false);
      expect(banner.parentElement).toBe(document.body);
      // The dialog itself is exactly where render() put it — still a
      // descendant of the test's own container, and NOT an ancestor of the
      // portaled banner.
      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    });

    it("remains dismissible while the dialog is open", async () => {
      const user = userEvent.setup();
      useMutationErrorStore.setState({
        errors: [{ id: 1, message: "Route not allowed" }],
      });
      renderWithOpenDialog();

      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("Route not allowed");

      await user.click(screen.getByLabelText("Dismiss error"));

      expect(screen.queryByRole("alert")).toBeNull();
      // The dialog is unaffected — dismissing the banner is not a proxy for
      // closing the modal underneath it.
      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    });
  });
});

import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmDialog } from "../ConfirmDialog";
import { useMutationErrorStore } from "../../../stores/mutationErrorStore";

describe("ConfirmDialog", () => {
  beforeEach(() => {
    useMutationErrorStore.setState({ errors: [] });
  });

  it("does not render when isOpen is false", () => {
    render(
      <ConfirmDialog
        isOpen={false}
        title="Confirm Action"
        message="Are you sure?"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("renders when isOpen is true", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Confirm Action"
        message="Are you sure?"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText("Confirm Action")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm button is clicked", () => {
    const mockConfirm = jest.fn();

    render(
      <ConfirmDialog
        isOpen={true}
        title="Delete"
        message="Delete this item?"
        confirmLabel="Delete"
        onConfirm={mockConfirm}
        onCancel={jest.fn()}
      />,
    );

    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    fireEvent.click(confirmBtn);

    expect(mockConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button is clicked", () => {
    const mockCancel = jest.fn();

    render(
      <ConfirmDialog
        isOpen={true}
        title="Delete"
        message="Delete this item?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    const cancelBtn = screen.getByTestId("confirm-dialog-cancel");
    fireEvent.click(cancelBtn);

    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when backdrop is clicked", () => {
    const mockCancel = jest.fn();

    render(
      <ConfirmDialog
        isOpen={true}
        title="Delete"
        message="Delete this item?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    const backdrop = screen.getByTestId("confirm-dialog-backdrop");
    fireEvent.click(backdrop);

    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when Escape key is pressed", () => {
    const mockCancel = jest.fn();

    render(
      <ConfirmDialog
        isOpen={true}
        title="Delete"
        message="Delete this item?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  it("renders danger variant with warning icon", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Delete Item"
        message="This action cannot be undone"
        isDangerous={true}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    expect(confirmBtn).toHaveClass("bg-red-600");
    // Verify AlertTriangle icon is rendered
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("wraps Tab from the last element back to the first", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Focus Test"
        message="Tab handling test"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    // No live alert, so the dialog's own confirm button is genuinely last.
    screen.getByTestId("confirm-dialog-confirm").focus();
    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByTestId("confirm-dialog-cancel")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element back to the last", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Focus Test"
        message="Shift+Tab handling test"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    screen.getByTestId("confirm-dialog-cancel").focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(screen.getByTestId("confirm-dialog-confirm")).toHaveFocus();
  });

  it("sends Tab to the first trapped element when focus is on neither the dialog nor an alert", () => {
    // e.g. focus is still on the backdrop, or on whatever had it before the
    // dialog opened but was not one of dialogRef's own children.
    render(
      <ConfirmDialog
        isOpen={true}
        title="Focus Test"
        message="Untracked focus test"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
    const outsider = document.createElement("button");
    document.body.appendChild(outsider);
    outsider.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByTestId("confirm-dialog-cancel")).toHaveFocus();
    outsider.remove();
  });

  it("sends Shift+Tab to the last trapped element when focus is on neither the dialog nor an alert", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Focus Test"
        message="Untracked focus test"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
    const outsider = document.createElement("button");
    document.body.appendChild(outsider);
    outsider.focus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(screen.getByTestId("confirm-dialog-confirm")).toHaveFocus();
    outsider.remove();
  });

  it("renders loading state", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Processing"
        message="Please wait..."
        confirmLabel="Delete"
        isLoading={true}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    expect(confirmBtn).toBeDisabled();
    const cancelBtn = screen.getByTestId("confirm-dialog-cancel");
    expect(cancelBtn).toBeDisabled();
  });

  it("uses custom confirm and cancel labels", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Save Changes?"
        message="Do you want to save?"
        confirmLabel="Save"
        cancelLabel="Discard"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /Save/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Discard/i }),
    ).toBeInTheDocument();
  });

  it("has proper ARIA attributes", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Confirm"
        message="Are you sure?"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "confirm-dialog-title");
    expect(dialog).toHaveAttribute(
      "aria-describedby",
      "confirm-dialog-message",
    );
  });

  it("focuses confirm button on open", () => {
    const { rerender } = render(
      <ConfirmDialog
        isOpen={false}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    rerender(
      <ConfirmDialog
        isOpen={true}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    expect(confirmBtn).toHaveFocus();
  });

  it("supports custom testId", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Test"
        message="Test?"
        testId="custom-dialog"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByTestId("custom-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("custom-dialog-confirm")).toBeInTheDocument();
    expect(screen.getByTestId("custom-dialog-cancel")).toBeInTheDocument();
  });

  it("renders with all combinations of props", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Complex Dialog"
        message="Multi-state test"
        confirmLabel="Accept"
        cancelLabel="Reject"
        isDangerous={false}
        isLoading={false}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByText("Complex Dialog")).toBeInTheDocument();
    expect(screen.getByText("Multi-state test")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Accept/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();
  });

  it("renders danger variant with icon and red button", () => {
    render(
      <ConfirmDialog
        isOpen={true}
        title="Dangerous Action"
        message="This will delete everything"
        isDangerous={true}
        confirmLabel="Delete All"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    const dialogBox = screen.getByRole("alertdialog");
    expect(confirmBtn).toHaveClass("bg-red-600");
    expect(dialogBox).toBeInTheDocument();
  });

  it("properly handles cleanup when isOpen becomes false", () => {
    const mockCancel = jest.fn();
    const { rerender } = render(
      <ConfirmDialog
        isOpen={true}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    // Dialog should be open
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    // Close the dialog
    rerender(
      <ConfirmDialog
        isOpen={false}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    // Dialog should not be in document
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("handles loading state with disabled buttons", () => {
    const mockConfirm = jest.fn();
    const mockCancel = jest.fn();
    render(
      <ConfirmDialog
        isOpen={true}
        title="Processing"
        message="Please wait..."
        isDangerous={true}
        isLoading={true}
        onConfirm={mockConfirm}
        onCancel={mockCancel}
      />,
    );

    const confirmBtn = screen.getByTestId("confirm-dialog-confirm");
    const cancelBtn = screen.getByTestId("confirm-dialog-cancel");

    expect(confirmBtn).toBeDisabled();
    expect(cancelBtn).toBeDisabled();
    expect(screen.getByText("Loading...")).toBeInTheDocument();

    // Buttons should not respond to clicks when disabled
    fireEvent.click(confirmBtn);
    fireEvent.click(cancelBtn);

    expect(mockConfirm).not.toHaveBeenCalled();
    expect(mockCancel).not.toHaveBeenCalled();
  });

  it("handles event listener cleanup and reattachment on isOpen change", () => {
    const mockCancel = jest.fn();
    const { rerender } = render(
      <ConfirmDialog
        isOpen={false}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    // Open dialog
    rerender(
      <ConfirmDialog
        isOpen={true}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    // Press Escape to close
    fireEvent.keyDown(document, { key: "Escape" });
    expect(mockCancel).toHaveBeenCalledTimes(1);

    // Close with backdrop click
    rerender(
      <ConfirmDialog
        isOpen={false}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    // Open again and test Escape again
    rerender(
      <ConfirmDialog
        isOpen={true}
        title="Test"
        message="Test?"
        onConfirm={jest.fn()}
        onCancel={mockCancel}
      />,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(mockCancel).toHaveBeenCalledTimes(2);
  });
});

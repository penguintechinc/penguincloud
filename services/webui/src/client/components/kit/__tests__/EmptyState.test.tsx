import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmptyState } from "../EmptyState";

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(
      <EmptyState
        title="No items found"
        description="There are no items to display"
      />,
    );

    expect(screen.getByText("No items found")).toBeInTheDocument();
    expect(
      screen.getByText("There are no items to display"),
    ).toBeInTheDocument();
  });

  it("renders with icon", () => {
    const TestIcon = () => <div data-testid="test-icon">🔍</div>;

    render(<EmptyState icon={<TestIcon />} title="No results" />);

    expect(screen.getByTestId("test-icon")).toBeInTheDocument();
  });

  it("renders action button and handles click", () => {
    const mockOnClick = jest.fn();

    render(
      <EmptyState
        title="No items"
        action={{
          label: "Create New",
          onClick: mockOnClick,
        }}
      />,
    );

    const button = screen.getByRole("button", { name: /Create New/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);
    expect(mockOnClick).toHaveBeenCalledTimes(1);
  });

  it("renders primary button variant", () => {
    render(
      <EmptyState
        title="Empty"
        action={{
          label: "Add Item",
          onClick: jest.fn(),
          variant: "primary",
        }}
      />,
    );

    const button = screen.getByRole("button", { name: /Add Item/i });
    expect(button).toHaveClass("bg-sky-500");
  });

  it("renders secondary button variant", () => {
    render(
      <EmptyState
        title="Empty"
        action={{
          label: "Cancel",
          onClick: jest.fn(),
          variant: "secondary",
        }}
      />,
    );

    const button = screen.getByRole("button", { name: /Cancel/i });
    expect(button).toHaveClass("bg-slate-700");
  });

  it("uses custom data-testid", () => {
    render(<EmptyState title="Empty" dataTestId="custom-empty" />);

    expect(screen.getByTestId("custom-empty")).toBeInTheDocument();
  });

  it("has proper ARIA attributes", () => {
    render(<EmptyState title="No data" icon={<div>📭</div>} />);

    expect(
      screen.getByRole("region", { name: /Empty state/i }),
    ).toBeInTheDocument();
    const icon = screen.getByText("📭");
    expect(icon.parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("renders without optional props", () => {
    render(<EmptyState title="Simple empty" />);

    expect(screen.getByText("Simple empty")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("button has focus styles", () => {
    render(
      <EmptyState
        title="Empty"
        action={{
          label: "Action",
          onClick: jest.fn(),
        }}
      />,
    );

    const button = screen.getByRole("button");
    expect(button).toHaveClass("focus:ring-2", "focus:ring-sky-500");
  });
});

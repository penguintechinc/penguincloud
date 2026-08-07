import { render, screen } from "@testing-library/react";
import StatusBadge from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders healthy status", () => {
    render(<StatusBadge status="healthy" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(badge).toHaveClass("bg-emerald-500/10");
  });

  it("renders degraded status", () => {
    render(<StatusBadge status="degraded" />);
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveClass("bg-amber-500/10");
  });

  it("renders unhealthy status", () => {
    render(<StatusBadge status="unhealthy" />);
    expect(screen.getByText("Unhealthy")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveClass("bg-red-500/10");
  });

  it("renders unknown status by default", () => {
    render(<StatusBadge status="unknown" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveClass("bg-slate-500/10");
  });

  it("supports all size variants", () => {
    const { rerender } = render(<StatusBadge status="healthy" size="sm" />);
    expect(screen.getByTestId("status-badge")).toHaveClass("px-2", "py-1");

    rerender(<StatusBadge status="healthy" size="md" />);
    expect(screen.getByTestId("status-badge")).toHaveClass("px-3", "py-1.5");

    rerender(<StatusBadge status="healthy" size="lg" />);
    expect(screen.getByTestId("status-badge")).toHaveClass("px-4", "py-2");
  });

  it("applies correct text colors", () => {
    const { rerender } = render(<StatusBadge status="healthy" size="sm" />);
    expect(screen.getByText("Healthy")).toHaveClass("text-emerald-400");

    rerender(<StatusBadge status="degraded" size="sm" />);
    expect(screen.getByText("Degraded")).toHaveClass("text-amber-400");

    rerender(<StatusBadge status="unhealthy" size="sm" />);
    expect(screen.getByText("Unhealthy")).toHaveClass("text-red-400");

    rerender(<StatusBadge status="unknown" size="sm" />);
    expect(screen.getByText("Unknown")).toHaveClass("text-slate-400");
  });

  it("has proper accessibility attributes", () => {
    render(<StatusBadge status="healthy" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveAttribute("role", "status");
    expect(badge).toHaveAttribute("aria-label", "Healthy");
  });

  it("renders with default size", () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByTestId("status-badge")).toHaveClass("px-3", "py-1.5");
  });
});

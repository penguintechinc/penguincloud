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

  it("renders down status", () => {
    render(<StatusBadge status="down" />);
    expect(screen.getByText("Down")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveClass("bg-red-500/10");
  });

  it("renders unknown status by default", () => {
    render(<StatusBadge status="unknown" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveClass("bg-slate-500/10");
  });

  it("supports size prop", () => {
    render(<StatusBadge status="healthy" size="lg" />);
    expect(screen.getByTestId("status-badge")).toHaveClass("px-4", "py-2");
  });

  it("has proper accessibility attributes", () => {
    render(<StatusBadge status="healthy" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveAttribute("role", "status");
    expect(badge).toHaveAttribute("aria-label", "Healthy");
  });
});

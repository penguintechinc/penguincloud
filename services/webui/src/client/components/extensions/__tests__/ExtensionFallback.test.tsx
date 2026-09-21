import { render, screen } from "@testing-library/react";
import { ExtensionFallback } from "../ExtensionFallback";

it("renders a non-blank panel carrying the given label", () => {
  render(<ExtensionFallback label="Billing Panel" />);

  const panel = screen.getByTestId("extension-fallback");
  expect(panel).toBeInTheDocument();
  expect(panel).toHaveTextContent("Billing Panel");
  expect(panel).toHaveTextContent(/not available/i);
});

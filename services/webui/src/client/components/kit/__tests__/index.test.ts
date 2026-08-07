/**
 * Test kit exports
 * Ensures all components are properly exported
 */
import * as kit from "../index";

describe("Kit exports", () => {
  it("exports StatusBadge", () => {
    expect(kit.StatusBadge).toBeDefined();
  });
});

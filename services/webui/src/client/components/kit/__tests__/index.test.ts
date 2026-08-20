/**
 * Test kit exports
 * Ensures all components are properly exported
 */
import * as kit from "../index";

describe("Kit exports", () => {
  it("exports StatusBadge", () => {
    expect(kit.StatusBadge).toBeDefined();
  });

  it("exports MutationErrorBanner", () => {
    expect(kit.MutationErrorBanner).toBeDefined();
  });

  it("exports the atoms promoted out of the product page directories", () => {
    // Gough and Nest reach these through the barrel now, not through a local
    // copy. A barrel that stopped exporting one would be a build error at
    // those call sites — but only for the products that already use it, so a
    // new screen importing from the barrel is the case this covers.
    expect(kit.ActionButton).toBeDefined();
    expect(kit.FactList).toBeDefined();
    expect(kit.RowOpenButtons).toBeDefined();
  });
});

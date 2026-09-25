/**
 * The `"{productType}.{id}"` cell registry in isolation from any render
 * path. Fixtures use an invented product type so a passing suite cannot be
 * explained by a hidden per-product branch in the resolver itself — mirrors
 * `ExtensionRegistry.test.ts`'s own discipline for the page registry.
 */
import {
  registerCellExtension,
  resolveCellExtension,
  clearCellExtensions,
  type ExtensionCellComponent,
} from "../ExtensionCellRegistry";

const NoopCell: ExtensionCellComponent = () => null;

afterEach(() => {
  clearCellExtensions();
});

it("resolves nothing for an unregistered key", () => {
  expect(
    resolveCellExtension("unregistered-product", "some_field"),
  ).toBeUndefined();
});

it('resolves the exact component registered under "{productType}.{id}"', () => {
  registerCellExtension("registry-product", "scope_id", NoopCell);

  expect(resolveCellExtension("registry-product", "scope_id")).toBe(NoopCell);
});

it("keys are composed from BOTH productType and id — neither alone matches", () => {
  registerCellExtension("registry-product", "scope_id", NoopCell);

  expect(
    resolveCellExtension("registry-product", "other_field"),
  ).toBeUndefined();
  expect(resolveCellExtension("other-product", "scope_id")).toBeUndefined();
});

it("a later registration for the same key overwrites the earlier one", () => {
  const first: ExtensionCellComponent = () => null;
  const second: ExtensionCellComponent = () => null;
  registerCellExtension("registry-product", "scope_id", first);
  registerCellExtension("registry-product", "scope_id", second);

  expect(resolveCellExtension("registry-product", "scope_id")).toBe(second);
});

it("clearCellExtensions removes every registered entry", () => {
  registerCellExtension("registry-product", "scope_id", NoopCell);

  clearCellExtensions();

  expect(resolveCellExtension("registry-product", "scope_id")).toBeUndefined();
});

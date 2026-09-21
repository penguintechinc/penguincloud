/**
 * The `"{productType}.{id}"` resolver in isolation from any render path.
 * Fixtures use an invented product type so a passing suite cannot be
 * explained by a hidden per-product branch in the resolver itself.
 */
import {
  registerPageExtension,
  resolveExtension,
  clearPageExtensions,
  type ExtensionLoader,
} from "../ExtensionRegistry";

const noopLoader: () => ExtensionLoader = () => () =>
  Promise.resolve({ default: () => null });

afterEach(() => {
  clearPageExtensions();
});

it("resolves nothing for an unregistered key", () => {
  expect(resolveExtension("unregistered-product", "some-slot")).toBeUndefined();
});

it('resolves the exact loader registered under "{productType}.{id}"', () => {
  const loader = noopLoader();
  registerPageExtension("registry-product", "panel-a", loader);

  expect(resolveExtension("registry-product", "panel-a")).toBe(loader);
});

it("keys are composed from BOTH productType and id — neither alone matches", () => {
  const loader = noopLoader();
  registerPageExtension("registry-product", "panel-a", loader);

  expect(resolveExtension("registry-product", "panel-b")).toBeUndefined();
  expect(resolveExtension("other-product", "panel-a")).toBeUndefined();
});

it("a later registration for the same key overwrites the earlier one", () => {
  const first = noopLoader();
  const second = noopLoader();
  registerPageExtension("registry-product", "panel-a", first);
  registerPageExtension("registry-product", "panel-a", second);

  expect(resolveExtension("registry-product", "panel-a")).toBe(second);
});

it("clearPageExtensions removes every registered entry", () => {
  registerPageExtension("registry-product", "panel-a", noopLoader());
  clearPageExtensions();

  expect(resolveExtension("registry-product", "panel-a")).toBeUndefined();
});

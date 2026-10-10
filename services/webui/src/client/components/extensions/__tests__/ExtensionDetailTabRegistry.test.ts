/**
 * The `"{productType}.{id}"` detail-tab registry in isolation from any
 * render path. Fixtures use an invented product type so a passing suite
 * cannot be explained by a hidden per-product branch in the resolver
 * itself — mirrors `ExtensionCellRegistry.test.ts`'s own discipline.
 */
import {
  registerDetailTabExtension,
  resolveDetailTabExtension,
  clearDetailTabExtensions,
  type ExtensionDetailTabLoader,
} from "../ExtensionDetailTabRegistry";

const noopLoader: ExtensionDetailTabLoader = () =>
  Promise.resolve({ default: () => null });

afterEach(() => {
  clearDetailTabExtensions();
});

it("resolves nothing for an unregistered key", () => {
  expect(
    resolveDetailTabExtension("unregistered-product", "health"),
  ).toBeUndefined();
});

it('resolves the exact loader registered under "{productType}.{id}"', () => {
  registerDetailTabExtension("registry-product", "health", noopLoader);

  expect(resolveDetailTabExtension("registry-product", "health")).toBe(
    noopLoader,
  );
});

it("keys are composed from BOTH productType and id — neither alone matches", () => {
  registerDetailTabExtension("registry-product", "health", noopLoader);

  expect(
    resolveDetailTabExtension("registry-product", "other-tab"),
  ).toBeUndefined();
  expect(resolveDetailTabExtension("other-product", "health")).toBeUndefined();
});

it("a later registration for the same key overwrites the earlier one", () => {
  const first: ExtensionDetailTabLoader = () =>
    Promise.resolve({ default: () => null });
  const second: ExtensionDetailTabLoader = () =>
    Promise.resolve({ default: () => null });
  registerDetailTabExtension("registry-product", "health", first);
  registerDetailTabExtension("registry-product", "health", second);

  expect(resolveDetailTabExtension("registry-product", "health")).toBe(second);
});

it("clearDetailTabExtensions removes every registered entry", () => {
  registerDetailTabExtension("registry-product", "health", noopLoader);

  clearDetailTabExtensions();

  expect(
    resolveDetailTabExtension("registry-product", "health"),
  ).toBeUndefined();
});

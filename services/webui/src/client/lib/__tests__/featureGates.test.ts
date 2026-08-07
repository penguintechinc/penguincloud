/**
 * Product feature gate tests.
 *
 * The gates are read once at module load, so each scenario re-imports the
 * module with a different VITE_ENABLE_PRODUCTS value. `lib/viteEnv` is stubbed
 * to read process.env (see jest.config.js moduleNameMapper).
 */

const ENV_KEY = "VITE_ENABLE_PRODUCTS";

async function loadGates(override?: string) {
  jest.resetModules();
  if (override === undefined) {
    delete process.env[ENV_KEY];
  } else {
    process.env[ENV_KEY] = override;
  }
  return import("../featureGates");
}

afterEach(() => {
  delete process.env[ENV_KEY];
});

describe("isProductEnabled", () => {
  it("defaults every product off", async () => {
    const { isProductEnabled } = await loadGates();

    expect(isProductEnabled("gough")).toBe(false);
    expect(isProductEnabled("nest")).toBe(false);
    expect(isProductEnabled("tobogganing")).toBe(false);
    expect(isProductEnabled("waddleai")).toBe(false);
    expect(isProductEnabled("waddlebot")).toBe(false);
    expect(isProductEnabled("elder")).toBe(false);
  });

  it("is false for an unknown product", async () => {
    const { isProductEnabled } = await loadGates();

    expect(isProductEnabled("not-a-product")).toBe(false);
  });

  it("enables the products named in the override", async () => {
    const { isProductEnabled } = await loadGates("gough,nest");

    expect(isProductEnabled("gough")).toBe(true);
    expect(isProductEnabled("nest")).toBe(true);
    expect(isProductEnabled("tobogganing")).toBe(false);
  });

  it("tolerates whitespace and empty entries", async () => {
    const { isProductEnabled } = await loadGates(" gough , , nest ,");

    expect(isProductEnabled("gough")).toBe(true);
    expect(isProductEnabled("nest")).toBe(true);
  });

  it("ignores an empty override", async () => {
    const { isProductEnabled } = await loadGates("");

    expect(isProductEnabled("gough")).toBe(false);
  });

  it("can enable a product with no default entry", async () => {
    const { isProductEnabled } = await loadGates("future-product");

    expect(isProductEnabled("future-product")).toBe(true);
  });
});

describe("getEnabledProducts", () => {
  it("is empty by default", async () => {
    const { getEnabledProducts } = await loadGates();

    expect(getEnabledProducts()).toEqual([]);
  });

  it("lists the overridden products", async () => {
    const { getEnabledProducts } = await loadGates("nest,elder");

    expect(getEnabledProducts().sort()).toEqual(["elder", "nest"]);
  });
});

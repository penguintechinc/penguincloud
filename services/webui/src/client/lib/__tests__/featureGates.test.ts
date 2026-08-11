/**
 * Feature gates, now served by the portal instead of baked into the bundle.
 *
 * These replace the `VITE_ENABLE_PRODUCTS` tests. That override was a
 * build-time seam: enabling a product for a customer meant rebuilding the
 * frontend image, and the browser's belief about what was on was a build
 * artefact that could differ from the portal's answer with nothing reporting
 * the disagreement. `GET /api/v1/features` is the single authority now.
 *
 * The property worth protecting is the DEFAULT: everything off until the
 * portal says otherwise, including when the fetch fails. A product briefly
 * hidden is a cosmetic delay; a product briefly shown is a screen that
 * renders and then vanishes.
 */

import { renderHook } from "@testing-library/react";
import type { FeaturesPayload } from "../../api/resources/features";
import {
  getEnabledProducts,
  isProductEnabled,
  useDevMode,
  useFeatureGateStore,
  useLicenseTier,
  useProductEnabled,
  useTierOrder,
} from "../featureGates";

function payload(overrides: Partial<FeaturesPayload> = {}): FeaturesPayload {
  return {
    flags: { gough: false, nest: false, tobogganing: false },
    tier: "community",
    tiers: ["community", "professional", "enterprise"],
    licensedFeatures: { sso_integration: "professional" },
    devMode: false,
    devModeMaxUsers: 1,
    limits: { tenants: 1, teams: 1, objects: 1000 },
    ...overrides,
  };
}

beforeEach(() => {
  useFeatureGateStore.setState({ features: null, loaded: false });
});

describe("isProductEnabled", () => {
  it("is false for every product before the portal answers", () => {
    expect(isProductEnabled("gough")).toBe(false);
    expect(isProductEnabled("nest")).toBe(false);
    expect(isProductEnabled("tobogganing")).toBe(false);
  });

  it("is false for an unknown product", () => {
    useFeatureGateStore.getState().setFeatures(payload());

    expect(isProductEnabled("not-a-product")).toBe(false);
  });

  it("reflects the portal's answer", () => {
    useFeatureGateStore
      .getState()
      .setFeatures(payload({ flags: { gough: true, nest: false } }));

    expect(isProductEnabled("gough")).toBe(true);
    expect(isProductEnabled("nest")).toBe(false);
  });

  it("falls back to off when the fetch failed", () => {
    useFeatureGateStore
      .getState()
      .setFeatures(payload({ flags: { gough: true } }));
    expect(isProductEnabled("gough")).toBe(true);

    // useFeatures publishes null on error rather than leaving a stale answer.
    useFeatureGateStore.getState().setFeatures(null);
    expect(isProductEnabled("gough")).toBe(false);
  });

  it("treats a non-boolean value as off", () => {
    // A response that got past the decoder would still not be trusted into
    // the truthy branch — the comparison is `=== true`, not a truthiness
    // check, so `"yes"` or `1` cannot enable a product.
    useFeatureGateStore
      .getState()
      .setFeatures(payload({ flags: { gough: "yes" as unknown as boolean } }));

    expect(isProductEnabled("gough")).toBe(false);
  });
});

describe("getEnabledProducts", () => {
  it("is empty before the portal answers", () => {
    expect(getEnabledProducts()).toEqual([]);
  });

  it("lists only the enabled flags", () => {
    useFeatureGateStore
      .getState()
      .setFeatures(
        payload({ flags: { gough: true, nest: false, elder: true } }),
      );

    expect(getEnabledProducts().sort()).toEqual(["elder", "gough"]);
  });
});

describe("store state", () => {
  it("records that a response was seen, even a failed one", () => {
    expect(useFeatureGateStore.getState().loaded).toBe(false);

    useFeatureGateStore.getState().setFeatures(null);

    expect(useFeatureGateStore.getState().loaded).toBe(true);
    expect(useFeatureGateStore.getState().features).toBeNull();
  });
});

describe("reactive gates", () => {
  it("useProductEnabled follows the store", () => {
    const { result, rerender } = renderHook(() => useProductEnabled("gough"));
    expect(result.current).toBe(false);

    useFeatureGateStore
      .getState()
      .setFeatures(payload({ flags: { gough: true } }));
    rerender();

    expect(result.current).toBe(true);
  });

  it("useLicenseTier is community until the portal says otherwise", () => {
    const { result, rerender } = renderHook(() => useLicenseTier());
    // The narrowest tier is the safe unknown: an unresolved licence must not
    // render enterprise surfaces that the server will then 403.
    expect(result.current).toBe("community");

    useFeatureGateStore.getState().setFeatures(payload({ tier: "enterprise" }));
    rerender();

    expect(result.current).toBe("enterprise");
  });

  it("useTierOrder falls back to the canonical ordering", () => {
    const { result, rerender } = renderHook(() => useTierOrder());
    expect(result.current).toEqual(["community", "professional", "enterprise"]);

    useFeatureGateStore
      .getState()
      .setFeatures(payload({ tiers: ["community", "enterprise"] }));
    rerender();

    expect(result.current).toEqual(["community", "enterprise"]);
  });

  it("useTierOrder returns a stable reference while unresolved", () => {
    // Not a style point: a selector building a new array each call makes
    // zustand's useSyncExternalStore see a changed snapshot every render and
    // loop until React throws "Maximum update depth exceeded". That is
    // exactly what the first version of this module did.
    const { result, rerender } = renderHook(() => useTierOrder());
    const first = result.current;
    rerender();

    expect(result.current).toBe(first);
  });

  it("useDevMode reports the server's signal, never an inference", () => {
    const { result, rerender } = renderHook(() => useDevMode());
    expect(result.current).toEqual({ active: false, maxUsers: 1 });

    useFeatureGateStore
      .getState()
      .setFeatures(payload({ devMode: true, devModeMaxUsers: 1 }));
    rerender();

    expect(result.current).toEqual({ active: true, maxUsers: 1 });
  });
});

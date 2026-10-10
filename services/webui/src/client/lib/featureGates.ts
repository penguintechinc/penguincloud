/**
 * Feature gates, served by the portal rather than baked into the bundle.
 *
 * What this replaced
 * ==================
 * A hardcoded `{gough: false, nest: false, ...}` map with a
 * `VITE_ENABLE_PRODUCTS` env override read once at module load. Enabling a
 * product for a customer meant rebuilding the frontend image, and the
 * browser's belief about what was on was a build artefact that could differ
 * from the portal's answer with nothing reporting the disagreement.
 *
 * Now: `GET /api/v1/features` is the single authority (PostHog flags AND the
 * licensed tier, resolved where they actually live), fetched once by
 * {@link useFeatures} and mirrored into this store.
 *
 * Why a store and not just the query
 * ==================================
 * `components/layout/menuCategories.ts` builds the sidebar from a plain
 * function, outside any component, so it cannot call a hook. A snapshot that
 * both a hook and a plain function can read is what lets one answer serve
 * both without keeping two.
 *
 * Everything defaults OFF until the fetch resolves, which is the same
 * fail-closed default the hardcoded map had. That is deliberate: a product
 * briefly hidden is a cosmetic delay, a product briefly shown is a screen
 * that renders and then vanishes. Note this is navigation only — the portal
 * refuses a proxy call for a connection the tenant does not own regardless of
 * what the browser believes.
 */

import { create } from "zustand";
import type { FeaturesPayload } from "../api/resources/features";

interface FeatureGateState {
  /** The portal's answer, or null before the first successful fetch. */
  features: FeaturesPayload | null;
  /** True once a response has been decoded, successfully or not. */
  loaded: boolean;
  setFeatures: (features: FeaturesPayload | null) => void;
}

/** Fallbacks held as constants so selectors return a stable reference. */
const DEFAULT_TIERS: string[] = ["community", "professional", "enterprise"];
const DEFAULT_DEV_MODE_MAX_USERS = 1;

export const useFeatureGateStore = create<FeatureGateState>((set) => ({
  features: null,
  loaded: false,
  setFeatures: (features) => set({ features, loaded: true }),
}));

/**
 * Whether a product category is enabled, read synchronously.
 *
 * For callers that are not components or hooks (the sidebar builder). Inside
 * a component, prefer {@link useProductEnabled} so the view re-renders when
 * the answer arrives.
 */
export function isProductEnabled(productKey: string): boolean {
  return useFeatureGateStore.getState().features?.flags[productKey] === true;
}

/** Reactive form of {@link isProductEnabled}. */
export function useProductEnabled(productKey: string): boolean {
  return useFeatureGateStore(
    (state) => state.features?.flags[productKey] === true,
  );
}

/** Every enabled flag key. Empty before the fetch resolves. */
export function getEnabledProducts(): string[] {
  const flags = useFeatureGateStore.getState().features?.flags ?? {};
  return Object.entries(flags)
    .filter(([, enabled]) => enabled)
    .map(([key]) => key);
}

/** The licensed tier, or `"community"` — the narrowest — before it is known. */
export function useLicenseTier(): string {
  return useFeatureGateStore((state) => state.features?.tier ?? "community");
}

/**
 * Tier ordering as the portal publishes it, narrowest first.
 *
 * The fallback is a module constant, not an inline literal. A selector that
 * builds a new array on every call returns a different snapshot each time,
 * and `useSyncExternalStore` (which zustand is built on) reacts to that by
 * re-rendering forever — "Maximum update depth exceeded".
 */
export function useTierOrder(): string[] {
  return useFeatureGateStore((state) => state.features?.tiers ?? DEFAULT_TIERS);
}

/**
 * True when `--dev` is ACTIVE on the server.
 *
 * Never inferred client-side. The three conditions (PenguinTech domain, at
 * most one user, flag passed) are all server-side facts, and the user count
 * in particular is exactly the thing a browser must not be trusted about.
 */
export function useDevMode(): { active: boolean; maxUsers: number } {
  // Two primitive selectors, deliberately, rather than one returning an
  // object: an object literal is a new reference every call, which zustand's
  // useSyncExternalStore reads as a changed snapshot and re-renders on
  // forever. The composed object below is built after the subscriptions and
  // is never what the store is compared against.
  const active = useFeatureGateStore(
    (state) => state.features?.devMode === true,
  );
  const maxUsers = useFeatureGateStore(
    (state) => state.features?.devModeMaxUsers ?? DEFAULT_DEV_MODE_MAX_USERS,
  );
  return { active, maxUsers };
}

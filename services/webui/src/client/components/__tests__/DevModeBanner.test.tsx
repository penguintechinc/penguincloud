/**
 * The persistent `--dev` banner.
 *
 * general.md requires a banner rather than a toast, and requires it be
 * non-dismissible: the person who needs to see it is usually not the person
 * who started the process, and someone opening the portal has no other way to
 * learn that every premium capability on screen is unlocked without a licence.
 *
 * The signal is server-side only. Two of the three activation conditions are
 * the deployment domain and the user count, and a count the browser could
 * influence is not a count — so this component renders a fact it is told,
 * never one it infers.
 */

import { render, screen } from "@testing-library/react";
import DevModeBanner from "../DevModeBanner";
import { useFeatureGateStore } from "../../lib/featureGates";
import type { FeaturesPayload } from "../../api/resources/features";

function payload(overrides: Partial<FeaturesPayload> = {}): FeaturesPayload {
  return {
    flags: {},
    tier: "community",
    tiers: ["community", "professional", "enterprise"],
    licensedFeatures: {},
    devMode: false,
    devModeMaxUsers: 1,
    limits: { tenants: 1, teams: 1, objects: 1000 },
    ...overrides,
  };
}

beforeEach(() => {
  useFeatureGateStore.setState({ features: null, loaded: false });
});

describe("DevModeBanner", () => {
  it("renders nothing before the portal answers", () => {
    render(<DevModeBanner />);

    expect(screen.queryByTestId("dev-mode-banner")).toBeNull();
  });

  it("renders nothing on a normal deployment", () => {
    useFeatureGateStore.getState().setFeatures(payload({ devMode: false }));

    render(<DevModeBanner />);

    expect(screen.queryByTestId("dev-mode-banner")).toBeNull();
  });

  it("renders when the server reports dev mode active", () => {
    useFeatureGateStore.getState().setFeatures(payload({ devMode: true }));

    render(<DevModeBanner />);

    expect(screen.getByTestId("dev-mode-banner")).toBeInTheDocument();
    expect(screen.getByText(/Development mode/i)).toBeInTheDocument();
  });

  it("states the licence obligation, not just the mode", () => {
    useFeatureGateStore.getState().setFeatures(payload({ devMode: true }));

    render(<DevModeBanner />);

    expect(
      screen.getByText(/breaches the PenguinTech licence terms/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/limited to 1 user/i)).toBeInTheDocument();
  });

  it("offers no way to dismiss it", () => {
    useFeatureGateStore.getState().setFeatures(payload({ devMode: true }));

    const { container } = render(<DevModeBanner />);
    const banner = screen.getByTestId("dev-mode-banner");

    // No close control of any kind: a dismissible banner is a banner that is
    // gone by the time it matters.
    expect(banner.querySelector("button")).toBeNull();
    expect(container.querySelectorAll('[aria-label*="ismiss"]')).toHaveLength(
      0,
    );
    expect(container.querySelectorAll('[aria-label*="lose"]')).toHaveLength(0);
  });

  it("disappears when the server stops reporting dev mode", () => {
    useFeatureGateStore.getState().setFeatures(payload({ devMode: true }));
    const { rerender } = render(<DevModeBanner />);
    expect(screen.getByTestId("dev-mode-banner")).toBeInTheDocument();

    // A second user was added; the server re-evaluates per request and the
    // banner must follow rather than latch.
    useFeatureGateStore.getState().setFeatures(payload({ devMode: false }));
    rerender(<DevModeBanner />);

    expect(screen.queryByTestId("dev-mode-banner")).toBeNull();
  });
});

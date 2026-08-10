/**
 * `GET /api/v1/features` decoding: a missing key is an error, never a default.
 *
 * The portal's `FeaturesResponse` declares all six fields as required, so an
 * absent one means the response is not the shape this client was written
 * against — a route that 404'd into an error page, a proxy returning the
 * upstream body, a schema that changed. Reading a missing `flags` as `{}`
 * would render every product as "behind a feature flag that is currently
 * off", which is a sentence an operator will believe and act on.
 *
 * Same rule the envelope helpers enforce for list and string keys; this file
 * is the boolean/number/map case.
 */

import { decodeFeatures } from "../features";

const complete = {
  flags: { gough: true, nest: false },
  tier: "professional",
  tiers: ["community", "professional", "enterprise"],
  licensed_features: { sso_integration: "professional" },
  dev_mode: false,
  dev_mode_max_users: 1,
};

describe("decodeFeatures", () => {
  it("decodes a complete response", () => {
    expect(decodeFeatures(complete)).toEqual({
      flags: { gough: true, nest: false },
      tier: "professional",
      tiers: ["community", "professional", "enterprise"],
      licensedFeatures: { sso_integration: "professional" },
      devMode: false,
      devModeMaxUsers: 1,
    });
  });

  it.each([
    "flags",
    "tier",
    "tiers",
    "licensed_features",
    "dev_mode",
    "dev_mode_max_users",
  ])("throws when %s is absent", (key) => {
    const partial: Record<string, unknown> = { ...complete };
    delete partial[key];

    expect(() => decodeFeatures(partial)).toThrow(new RegExp(`"${key}"`));
  });

  it("names the keys it did receive, so the failure is diagnosable", () => {
    expect(() => decodeFeatures({ tier: "community" })).toThrow(/tier/);
  });

  it.each([null, undefined, [], "a string", 7])(
    "throws on a non-object body (%p)",
    (body) => {
      expect(() => decodeFeatures(body)).toThrow(/features envelope/);
    },
  );

  it("throws on a flag value that is not a boolean", () => {
    expect(() =>
      decodeFeatures({ ...complete, flags: { gough: "yes" } }),
    ).toThrow(/flags\.gough/);
  });

  it("throws when flags is not an object", () => {
    expect(() => decodeFeatures({ ...complete, flags: ["gough"] })).toThrow(
      /"flags" is not an object/,
    );
  });

  it("throws on a licensed_features value that is not a string", () => {
    expect(() =>
      decodeFeatures({ ...complete, licensed_features: { sso: 3 } }),
    ).toThrow(/licensed_features\.sso/);
  });

  it("throws when licensed_features is not an object", () => {
    expect(() =>
      decodeFeatures({ ...complete, licensed_features: "professional" }),
    ).toThrow(/"licensed_features" is not an object/);
  });

  it("throws when tier is not a string", () => {
    expect(() => decodeFeatures({ ...complete, tier: 2 })).toThrow(
      /"tier" is not a string/,
    );
  });

  it("throws when tiers is not an array", () => {
    expect(() => decodeFeatures({ ...complete, tiers: "community" })).toThrow(
      /"tiers" is not an array/,
    );
  });

  it("throws when tiers holds a non-string", () => {
    expect(() =>
      decodeFeatures({ ...complete, tiers: ["community", 2] }),
    ).toThrow(/"tiers" holds a non-string/);
  });

  it("throws when dev_mode is not a boolean", () => {
    expect(() => decodeFeatures({ ...complete, dev_mode: "true" })).toThrow(
      /"dev_mode" is not a boolean/,
    );
  });

  it("throws when dev_mode_max_users is not a number", () => {
    expect(() =>
      decodeFeatures({ ...complete, dev_mode_max_users: "1" }),
    ).toThrow(/"dev_mode_max_users" is not a number/);
  });

  it("accepts an empty flag map without inventing entries", () => {
    // Distinct from a MISSING key: the portal genuinely publishing zero
    // flags is a legitimate (if unlikely) answer, and must not throw.
    expect(decodeFeatures({ ...complete, flags: {} }).flags).toEqual({});
  });
});

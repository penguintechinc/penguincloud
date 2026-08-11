/**
 * `GET /api/v1/features` — flag state, licensed tier, dev-mode signal.
 *
 * Replaces the build-time seam in `lib/featureGates.ts`, which held a
 * hardcoded all-false map plus a `VITE_ENABLE_PRODUCTS` override. Enabling a
 * product for a customer was a frontend rebuild, and the browser's idea of
 * what was on could differ from the portal's with nothing reporting the
 * disagreement.
 *
 * Every key is decoded strictly. The portal's `FeaturesResponse` DTO declares
 * all six fields as required, so an absent one is not "the default" — it is a
 * shape this client was not written against (a route that 404'd into an error
 * page, a proxy returning something else, a schema that changed). Reading a
 * missing `flags` as `{}` would render every product as "behind a feature
 * flag that is currently off", which is a sentence an operator will believe.
 */

import api from "../../lib/api";
import { portalUrl } from "../portalPaths";

/** The portal's `FeaturesResponse`, one field per DTO field. */
export interface FeaturesPayload {
  /** Every declared flag by feature name, always complete. */
  flags: Record<string, boolean>;
  /** community | professional | enterprise. */
  tier: string;
  /** Every tier, narrowest first. */
  tiers: string[];
  /** Licensed feature -> minimum tier required for it. */
  licensedFeatures: Record<string, string>;
  /** True when `--dev` is ACTIVE, not merely requested. */
  devMode: boolean;
  /** How many users dev mode permits. */
  devModeMaxUsers: number;
  /** Effective scale/structure limits by dimension; -1 means unlimited. */
  limits: Record<string, number>;
}

function requireKey(payload: unknown, key: string): unknown {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`no features envelope carrying "${key}"`);
  }
  const record = payload as Record<string, unknown>;
  if (!(key in record)) {
    throw new Error(
      `no "${key}" key (got ${JSON.stringify(Object.keys(record))}) — ` +
        `refusing to treat it as a default`,
    );
  }
  return record[key];
}

function requireBooleanMap(
  payload: unknown,
  key: string,
): Record<string, boolean> {
  const value = requireKey(payload, key);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`"${key}" is not an object`);
  }
  const result: Record<string, boolean> = {};
  for (const [name, entry] of Object.entries(value)) {
    if (typeof entry !== "boolean") {
      throw new Error(`"${key}.${name}" is not a boolean`);
    }
    result[name] = entry;
  }
  return result;
}

function requireNumberMap(
  payload: unknown,
  key: string,
): Record<string, number> {
  const value = requireKey(payload, key);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`"${key}" is not an object`);
  }
  const result: Record<string, number> = {};
  for (const [name, entry] of Object.entries(value)) {
    if (typeof entry !== "number") {
      throw new Error(`"${key}.${name}" is not a number`);
    }
    result[name] = entry;
  }
  return result;
}

function requireStringMap(
  payload: unknown,
  key: string,
): Record<string, string> {
  const value = requireKey(payload, key);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`"${key}" is not an object`);
  }
  const result: Record<string, string> = {};
  for (const [name, entry] of Object.entries(value)) {
    if (typeof entry !== "string") {
      throw new Error(`"${key}.${name}" is not a string`);
    }
    result[name] = entry;
  }
  return result;
}

function requireString(payload: unknown, key: string): string {
  const value = requireKey(payload, key);
  if (typeof value !== "string") throw new Error(`"${key}" is not a string`);
  return value;
}

function requireStringList(payload: unknown, key: string): string[] {
  const value = requireKey(payload, key);
  if (!Array.isArray(value)) throw new Error(`"${key}" is not an array`);
  return value.map((entry) => {
    if (typeof entry !== "string")
      throw new Error(`"${key}" holds a non-string`);
    return entry;
  });
}

function requireBoolean(payload: unknown, key: string): boolean {
  const value = requireKey(payload, key);
  if (typeof value !== "boolean") throw new Error(`"${key}" is not a boolean`);
  return value;
}

function requireNumber(payload: unknown, key: string): number {
  const value = requireKey(payload, key);
  if (typeof value !== "number") throw new Error(`"${key}" is not a number`);
  return value;
}

/** Decode the portal's response, throwing on anything unexpected. */
export function decodeFeatures(payload: unknown): FeaturesPayload {
  return {
    flags: requireBooleanMap(payload, "flags"),
    tier: requireString(payload, "tier"),
    tiers: requireStringList(payload, "tiers"),
    licensedFeatures: requireStringMap(payload, "licensed_features"),
    devMode: requireBoolean(payload, "dev_mode"),
    devModeMaxUsers: requireNumber(payload, "dev_mode_max_users"),
    limits: requireNumberMap(payload, "limits"),
  };
}

export const featuresApi = {
  get: async (): Promise<FeaturesPayload> => {
    const response = await api.get(portalUrl.features());
    return decodeFeatures(response.data);
  },
};

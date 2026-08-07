/**
 * Feature gates for product categories. Hardcoded defaults OFF until PostHog client lands (Phase 5).
 * Override via VITE_ENABLE_PRODUCTS env var: comma-separated list of product keys (e.g., "gough,nest,tobogganing").
 */

import { readEnv } from "./viteEnv";

const DEFAULT_GATES: Record<string, boolean> = {
  gough: false,
  nest: false,
  tobogganing: false,
  waddleai: false,
  waddlebot: false,
  elder: false,
};

function parseEnvOverride(): Record<string, boolean> {
  const envValue = readEnv("VITE_ENABLE_PRODUCTS");
  if (!envValue) return {};

  const enabled = envValue.split(",").map((s: string) => s.trim());
  const result: Record<string, boolean> = {};
  for (const key of enabled) {
    if (key) result[key] = true;
  }
  return result;
}

const envOverrides = parseEnvOverride();

/**
 * Check if a product category feature gate is enabled.
 * @param productKey - Product key (e.g., 'gough', 'nest')
 * @returns true if enabled, false otherwise
 */
export function isProductEnabled(productKey: string): boolean {
  return envOverrides[productKey] ?? DEFAULT_GATES[productKey] ?? false;
}

/**
 * Get all enabled product keys.
 * @returns array of enabled product keys
 */
export function getEnabledProducts(): string[] {
  const gates = { ...DEFAULT_GATES, ...envOverrides };
  return Object.entries(gates)
    .filter(([, enabled]) => enabled)
    .map(([key]) => key);
}

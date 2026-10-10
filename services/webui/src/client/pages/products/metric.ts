/**
 * Display helpers for untyped product-proxy responses.
 *
 * Each product exposes its own status payload, so the proxy returns
 * `Record<string, unknown>` rather than a per-product interface. These helpers
 * narrow a single field to something React can actually render, replacing the
 * `(data as any)?.field ?? "—"` casts the Overview pages previously used.
 */

/** Value kinds React can render directly. */
export type MetricValue = string | number;

/**
 * Reads one metric off a product status payload for display.
 *
 * Returns `fallback` when the key is absent, null, or holds a non-primitive.
 * The non-primitive guard matters: rendering a raw object or array inside JSX
 * throws at runtime, and an `any` cast would have let that through silently.
 */
export function metric(
  data: Record<string, unknown> | null | undefined,
  key: string,
  fallback: MetricValue = "—",
): MetricValue {
  const value = data?.[key];

  if (typeof value === "string" || typeof value === "number") {
    return value;
  }

  return fallback;
}

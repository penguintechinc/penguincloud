import { Suspense, lazy, useMemo } from "react";
import {
  resolveDetailTabExtension,
  type ExtensionDetailTabProps,
} from "./ExtensionDetailTabRegistry";
import { ExtensionFallback } from "./ExtensionFallback";

/** Shown while the resolved extension's own chunk is still loading — same
 * shell `ExtensionSlotRenderer.tsx` uses for a page slot, reused rather than
 * duplicated since a drawer tab body has the exact same "still loading"
 * shape as a whole page does. */
function ExtensionDetailTabLoadingPanel() {
  return (
    <div
      className="animate-pulse h-32 bg-slate-700 rounded"
      data-testid="extension-detail-tab-loading"
      role="status"
      aria-label="Loading extension"
    />
  );
}

/**
 * The registry lookup + render decision for a `detail_tab` slot, in
 * isolation from `ManifestResourceDetail`'s tab assembly: given a resolved
 * manifest slot and the open row, resolve `"{productType}.{slot.id}"`
 * against {@link resolveDetailTabExtension} and either render it lazily
 * inside a `Suspense` boundary, or degrade to {@link ExtensionFallback} —
 * Design §3.4, mirroring `ExtensionSlotRenderer.tsx`'s own page-slot
 * discipline exactly (same Suspense-lazy posture, same fallback component).
 * Nothing here names a product: the same component instantiated for any
 * `productType`/`slot.id`/row combination is the whole mechanism.
 */
export function ExtensionDetailTabSlot({
  productType,
  productId,
  tenantId,
  row,
  slot,
}: ExtensionDetailTabProps) {
  const loader = resolveDetailTabExtension(productType, slot.id);

  // `useMemo` keyed on the loader reference (stable across renders — the
  // registry never replaces an entry's function identity once registered)
  // so `React.lazy` is not re-invoked, and the Suspense boundary below does
  // not remount, on every render of this component — matching
  // `ExtensionSlotRenderer.tsx`'s own rationale.
  const LazyExtension = useMemo(() => (loader ? lazy(loader) : null), [loader]);

  if (!LazyExtension) {
    return <ExtensionFallback label={slot.label} />;
  }

  return (
    <Suspense fallback={<ExtensionDetailTabLoadingPanel />}>
      <LazyExtension
        productType={productType}
        productId={productId}
        tenantId={tenantId}
        row={row}
        slot={slot}
      />
    </Suspense>
  );
}

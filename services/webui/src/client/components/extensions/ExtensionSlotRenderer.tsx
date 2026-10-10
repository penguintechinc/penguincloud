import { Suspense, lazy, useMemo } from "react";
import { resolveExtension, type ExtensionPageProps } from "./ExtensionRegistry";
import { ExtensionFallback } from "./ExtensionFallback";

/** Shown while the resolved extension's own chunk is still loading. */
function ExtensionLoadingPanel() {
  return (
    <div
      className="animate-pulse h-48 bg-slate-700 rounded"
      data-testid="extension-loading"
      role="status"
      aria-label="Loading extension"
    />
  );
}

/**
 * The registry lookup + render decision, in isolation from routing/nav:
 * given a resolved manifest slot, resolve `"{productType}.{slot.id}"`
 * against {@link resolveExtension} and either render it lazily inside a
 * `Suspense` boundary, or degrade to {@link ExtensionFallback} — Design
 * §3.4. Nothing here names a product: the same component instantiated for
 * any `productType`/`slot.id` pair is the whole mechanism.
 */
export function ExtensionSlotRenderer({
  productType,
  productId,
  tenantId,
  slot,
}: ExtensionPageProps) {
  const loader = resolveExtension(productType, slot.id);

  // `useMemo` keyed on the loader reference (stable across renders — the
  // registry never replaces an entry's function identity once registered)
  // so `React.lazy` is not re-invoked, and the Suspense boundary below does
  // not remount, on every render of this component.
  const LazyExtension = useMemo(() => (loader ? lazy(loader) : null), [loader]);

  if (!LazyExtension) {
    return <ExtensionFallback label={slot.label} />;
  }

  return (
    <Suspense fallback={<ExtensionLoadingPanel />}>
      <LazyExtension
        productType={productType}
        productId={productId}
        tenantId={tenantId}
        slot={slot}
      />
    </Suspense>
  );
}

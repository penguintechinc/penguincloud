/**
 * The generic router-slot decision: render one product resource from its
 * committed manifest via {@link ManifestResourceScreen}, or fall back to the
 * hand-written screen `App.tsx` already routes to, so this step ships with
 * zero behaviour change while `penguincloud.declarative_console` is off and
 * zero regression for a product whose manifest declares more than the
 * renderer can yet reproduce losslessly.
 *
 * Every route-level fact this component needs — which product, which
 * resource kind, which manifest, whether that manifest's declared
 * capabilities are covered — is read off `useConsoleManifests()` and
 * `manifestCapabilities.ts`. Nothing here names a product: the same
 * component instantiated with a different `productType`/`kind`/`fallback`
 * is how every remaining hand-written product route in `App.tsx` is wired,
 * and it is also how a brand new read-only product would be wired with no
 * new decision logic — see `manifestCapabilities.ts`'s module doc.
 *
 * `fallback` is now OPTIONAL (Phase 8 Step 7): once Gough's and
 * Tobogganing's converged hand-written screens were deleted in favour of
 * the manifest console (default-on), their routes have no hand-written
 * screen left to fall back to. A route that still has one (Nest's
 * `DatabasesPage`/`BillingPage` — no committed manifest yet; Tobogganing's
 * `SwgPolicyPage` — unresolved `scope_id` ceiling) keeps passing it
 * unchanged.
 *
 * Four states, in order:
 * 1. No manifest for this (product, kind) yet — flag off (the endpoint
 *    403s, so `useConsoleManifests` never resolves `data`), still loading,
 *    or this product/kind simply has no committed manifest (e.g. Nest) —
 *    render the fallback if one was given. This is the "no behaviour
 *    change" default for a route that still has a hand-written screen.
 * 2. A manifest exists but declares capabilities the renderer cannot yet
 *    reproduce losslessly (`isManifestRoutable` false) — same as above.
 * 3. A manifest exists and is fully within `SUPPORTED_CAPABILITIES` —
 *    render `ManifestResourceScreen`.
 * 4. Neither (1)/(2) resolved AND no `fallback` was given — render
 *    {@link DefaultResourceFallback}, a generic connection-aware empty
 *    state, never blank and never a crash.
 */
import type { ComponentType } from "react";
import { useConsoleManifests } from "./useConsoleManifests";
import { ManifestResourceScreen } from "./ManifestResourceScreen";
import { findResource } from "./manifestTypes";
import { isManifestRoutable } from "./manifestCapabilities";
import { ProductScreen } from "./ProductScreen";
import { EmptyState } from "./EmptyState";
import { useProductConnection } from "./useProductResource";

export interface ProductResourceRouteProps {
  /** e.g. `"gough"` — the same key `useProductEnabled`/`useProductConnection`
   * and the manifest's own `product_type` use. */
  productType: string;
  /** Resource kind within the product's manifest, e.g. `"nodes"`. */
  kind: string;
  /**
   * The existing hand-written screen for this route — rendered unchanged
   * whenever the manifest cannot fully cover this resource yet. Optional:
   * a route with no hand-written screen left renders
   * {@link DefaultResourceFallback} instead.
   */
  fallback?: ComponentType;
}

/** `"gough"` -> `"Gough"` — used only when no manifest has resolved yet to
 * supply a real `display_name` (flag off, still loading, or a product with
 * no committed manifest and no `fallback`). Every call site passes a
 * non-empty route-param literal (`App.tsx`'s own `productType` props), so
 * this is a plain transform, not a defensive empty-string branch. */
function defaultProductLabel(productType: string): string {
  return productType.charAt(0).toUpperCase() + productType.slice(1);
}

/**
 * The generic placeholder for a resource route with no hand-written screen
 * left (Phase 8 Step 7 deleted Gough's and Tobogganing's converged
 * screens). Reuses `ProductScreen`'s own flag/connection gates — the same
 * "not enabled" / "no connection" affordance every hand-written product
 * screen showed via `GoughScreen.tsx`/`TobogganingScreen.tsx` — so a
 * disconnected or disabled tenant sees the identical message it always did;
 * only the "connected but this resource has no manifest coverage" case is
 * new copy, since no hand-written screen ever covered that case either.
 */
function DefaultResourceFallback({
  productType,
  kind,
  productLabel,
}: {
  productType: string;
  kind: string;
  productLabel: string;
}) {
  const { productId, isLoading } = useProductConnection(productType);
  const kindLabel = kind.replace(/_/g, " ");
  return (
    <ProductScreen
      productType={productType}
      productLabel={productLabel}
      title={productLabel}
      description={`${productLabel} ${kindLabel}`}
      productId={productId}
      isConnectionLoading={isLoading}
      noConnectionReason={`view its ${kindLabel}.`}
    >
      <EmptyState
        title="Not available"
        description={`This resource is not currently available for ${productLabel}.`}
        dataTestId={`${productType}-${kind}-unavailable`}
      />
    </ProductScreen>
  );
}

/** One product route slot: manifest-driven when it safely can be, the
 * existing hand-written screen when one was given, otherwise a generic
 * connection-aware empty state. */
export function ProductResourceRoute({
  productType,
  kind,
  fallback: Fallback,
}: ProductResourceRouteProps) {
  const manifestsQuery = useConsoleManifests();
  const entry = manifestsQuery.data?.find(
    (item) => item.product_type === productType,
  );
  const resource = entry ? findResource(entry.manifest, kind) : undefined;

  if (entry && resource && isManifestRoutable(entry.manifest, resource)) {
    return (
      <ManifestResourceScreen
        productType={productType}
        productLabel={entry.manifest.display_name}
        manifest={entry.manifest}
        resource={resource}
      />
    );
  }

  if (Fallback) {
    return <Fallback />;
  }

  return (
    <DefaultResourceFallback
      productType={productType}
      kind={kind}
      productLabel={
        entry?.manifest.display_name ?? defaultProductLabel(productType)
      }
    />
  );
}

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
 * is how every existing product route in `App.tsx` is wired, and it is also
 * how a brand new read-only product would be wired with no new decision
 * logic — see `manifestCapabilities.ts`'s module doc.
 *
 * Three states, in order:
 * 1. No manifest for this (product, kind) yet — flag off (the endpoint
 *    403s, so `useConsoleManifests` never resolves `data`), still loading,
 *    or this product/kind simply has no committed manifest (e.g. Nest) —
 *    render the fallback. This is the "no behaviour change" default.
 * 2. A manifest exists but declares capabilities the renderer cannot yet
 *    reproduce losslessly (`isManifestRoutable` false) — render the
 *    fallback. This is the "no regression" guard.
 * 3. A manifest exists and is fully within `SUPPORTED_CAPABILITIES` —
 *    render `ManifestResourceScreen`.
 */
import type { ComponentType } from "react";
import { useConsoleManifests } from "./useConsoleManifests";
import { ManifestResourceScreen } from "./ManifestResourceScreen";
import { findResource } from "./manifestTypes";
import { isManifestRoutable } from "./manifestCapabilities";

export interface ProductResourceRouteProps {
  /** e.g. `"gough"` — the same key `useProductEnabled`/`useProductConnection`
   * and the manifest's own `product_type` use. */
  productType: string;
  /** Resource kind within the product's manifest, e.g. `"nodes"`. */
  kind: string;
  /** The existing hand-written screen for this route — rendered unchanged
   * whenever the manifest cannot fully cover this resource yet. */
  fallback: ComponentType;
}

/** One product route slot: manifest-driven when it safely can be, the
 * existing hand-written screen otherwise. */
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

  return <Fallback />;
}

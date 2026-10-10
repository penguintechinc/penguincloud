import { useParams } from "react-router";
import { useConsoleManifests } from "../kit/useConsoleManifests";
import { useActiveTenantId } from "../kit/useProductResource";
import { ExtensionSlotRenderer } from "./ExtensionSlotRenderer";
import { ExtensionFallback } from "./ExtensionFallback";

/**
 * The single, generic route every `page`-slot extension mounts through —
 * `/products/:productType/ext/:extensionId` in `App.tsx`. No product name
 * anywhere in this file: the URL params ARE the product/slot identity,
 * matched against `useConsoleManifests()` the same way `ProductResourceRoute`
 * matches a resource kind against a manifest's `resources` list.
 *
 * Gating is inherited, not re-implemented here: `useConsoleManifests` only
 * resolves an entry when `penguincloud.declarative_console` is on AND the
 * tenant is connected to that product (the endpoint 403s otherwise, per that
 * hook's own doc) — this route never checks the flag or a connection
 * itself, matching `ProductResourceRoute`'s own "no behaviour change while
 * off" discipline.
 *
 * Deliberately independent of `manifestCapabilities.ts`
 * (`isManifestRoutable`/`requiredCapabilities`): a `page` slot is not a
 * resource and never was, so it does not go through the capability-subset
 * gate resources do — its own manifest presence (this file's own lookup) is
 * the whole gate.
 */
export function ExtensionPageRoute() {
  const { productType, extensionId } = useParams<{
    productType: string;
    extensionId: string;
  }>();
  const tenantId = useActiveTenantId();
  const manifestsQuery = useConsoleManifests();

  if (manifestsQuery.isLoading) {
    return (
      <div
        className="animate-pulse h-48 bg-slate-700 rounded"
        data-testid="extension-route-loading"
      />
    );
  }

  const entry = manifestsQuery.data?.find(
    (item) => item.product_type === productType,
  );
  const slot = entry?.manifest.extensions.find(
    (candidate) => candidate.slot === "page" && candidate.id === extensionId,
  );

  // No manifest for this product, or this manifest no longer declares this
  // slot (stale/typo'd URL) — degrade to the same generic fallback an
  // unregistered-but-declared slot renders, never a blank page.
  if (!entry || !slot || tenantId === undefined) {
    return <ExtensionFallback label={extensionId ?? "extension"} />;
  }

  return (
    <ExtensionSlotRenderer
      productType={entry.product_type}
      productId={entry.product_id}
      tenantId={tenantId}
      slot={slot}
    />
  );
}

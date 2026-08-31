import type { ReactNode } from "react";
import { EmptyState } from "./EmptyState";
import { useProductEnabled } from "../../lib/featureGates";

export interface ProductScreenProps {
  /**
   * The product's flag/connection key, e.g. `"gough"`. Drives the PostHog
   * flag lookup (`useProductEnabled`) and is the root of every generated
   * `data-testid` (`{productType}-disabled`, `{productType}-loading`,
   * `{productType}-no-connection`, `{productType}-screen`) — a caller
   * migrating off a product-specific shell keeps the same test ids for free.
   */
  productType: string;
  /** Display name used to compose the gate copy, e.g. `"Gough"`. */
  productLabel: string;
  title: string;
  description: string;
  productId: number | undefined;
  isConnectionLoading: boolean;
  children: ReactNode;
  /**
   * Product-specific tail of the no-connection message, appended after
   * "Register a {productLabel} connection for this tenant to ", e.g.
   * `"manage its fleet."`.
   */
  noConnectionReason: string;
}

/**
 * Shell shared by every product screen: flag gate, then connection gate,
 * then header, then content.
 *
 * Both gates are applied here rather than in each page so a new screen
 * cannot ship with one of them missing — the failure mode is a page that
 * renders product data for a tenant that has no such product, or with the
 * feature flag off, and neither is visible by looking at the page that
 * forgot.
 *
 * The flag is checked client-side for navigation only. It is not the
 * security control: the portal refuses a proxy call for a connection the
 * tenant does not own regardless of what the browser believes, and
 * `products:{productType}:*` scopes are only minted for tenants actually
 * connected to that product.
 */
export function ProductScreen({
  productType,
  productLabel,
  title,
  description,
  productId,
  isConnectionLoading,
  children,
  noConnectionReason,
}: ProductScreenProps) {
  // Hook call hoisted out of the `if` so it is unconditional at the top of
  // the component — rules-of-hooks, and it reads better besides.
  const isEnabled = useProductEnabled(productType);

  if (!isEnabled) {
    return (
      <EmptyState
        title={`${productLabel} is not enabled`}
        description="This product category is behind a feature flag that is currently off."
        dataTestId={`${productType}-disabled`}
      />
    );
  }

  if (isConnectionLoading) {
    return (
      <div
        className="animate-pulse h-48 bg-slate-700 rounded"
        data-testid={`${productType}-loading`}
      />
    );
  }

  if (productId === undefined) {
    return (
      <EmptyState
        title={`No ${productLabel} connection`}
        description={`Register a ${productLabel} connection for this tenant to ${noConnectionReason}`}
        dataTestId={`${productType}-no-connection`}
      />
    );
  }

  return (
    <div data-testid={`${productType}-screen`}>
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">{title}</h1>
        <p className="text-slate-400 text-sm mt-1">{description}</p>
      </header>
      {children}
    </div>
  );
}

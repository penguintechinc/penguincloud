import type { ReactNode } from "react";
import { EmptyState } from "../../../components/kit";
import { isProductEnabled } from "../../../lib/featureGates";

interface GoughScreenProps {
  title: string;
  description: string;
  productId: number | undefined;
  isConnectionLoading: boolean;
  children: ReactNode;
}

/**
 * Shell shared by every Gough screen: gate, then connection, then content.
 *
 * Both gates are applied here rather than in each page so a new screen cannot
 * ship with one of them missing — the failure mode is a page that renders
 * product data for a tenant that has no such product, or with the feature
 * flag off, and neither is visible by looking at the page that forgot.
 *
 * The flag is checked client-side for navigation only. It is not the security
 * control: the portal refuses a proxy call for a connection the tenant does
 * not own regardless of what the browser believes, and `products:gough:*`
 * scopes are only minted for tenants actually connected to Gough.
 */
export function GoughScreen({
  title,
  description,
  productId,
  isConnectionLoading,
  children,
}: GoughScreenProps) {
  if (!isProductEnabled("gough")) {
    return (
      <EmptyState
        title="Gough is not enabled"
        description="This product category is behind a feature flag that is currently off."
        dataTestId="gough-disabled"
      />
    );
  }

  if (isConnectionLoading) {
    return (
      <div
        className="animate-pulse h-48 bg-slate-700 rounded"
        data-testid="gough-loading"
      />
    );
  }

  if (productId === undefined) {
    return (
      <EmptyState
        title="No Gough connection"
        description="Register a Gough connection for this tenant to manage its fleet."
        dataTestId="gough-no-connection"
      />
    );
  }

  return (
    <div data-testid="gough-screen">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">{title}</h1>
        <p className="text-slate-400 text-sm mt-1">{description}</p>
      </header>
      {children}
    </div>
  );
}

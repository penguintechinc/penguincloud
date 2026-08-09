import type { ReactNode } from "react";
import { EmptyState } from "../../../components/kit";
import { isProductEnabled } from "../../../lib/featureGates";

interface TobogganingScreenProps {
  title: string;
  description: string;
  productId: number | undefined;
  isConnectionLoading: boolean;
  children: ReactNode;
}

/**
 * Shell shared by every Tobogganing screen: gate, then connection, then content.
 *
 * Both gates live here rather than in each page so a new screen cannot ship
 * with one of them missing — the failure mode is a page rendering product data
 * for a tenant that has no such product, or with the feature flag off, and
 * neither is visible by looking at the page that forgot.
 *
 * This check is the RENDER gate only. The fetch gate is in
 * `useTobogganingConnection`, and both are required: hooks run before a
 * component decides what to render, so a screen that returned this placeholder
 * without the hook-level gate would have already pulled the tenant's fleet into
 * the cache. The Gough phase shipped exactly that.
 *
 * The flag is not the security control either. The portal refuses a proxy call
 * for a connection the tenant does not own regardless of what the browser
 * believes, and `products:tobogganing:*` scopes are only minted for tenants
 * actually connected to Tobogganing.
 */
export function TobogganingScreen({
  title,
  description,
  productId,
  isConnectionLoading,
  children,
}: TobogganingScreenProps) {
  if (!isProductEnabled("tobogganing")) {
    return (
      <EmptyState
        title="Tobogganing is not enabled"
        description="This product category is behind a feature flag that is currently off."
        dataTestId="tobogganing-disabled"
      />
    );
  }

  if (isConnectionLoading) {
    return (
      <div
        className="animate-pulse h-48 bg-slate-700 rounded"
        data-testid="tobogganing-loading"
      />
    );
  }

  if (productId === undefined) {
    return (
      <EmptyState
        title="No Tobogganing connection"
        description="Register a Tobogganing connection for this tenant to manage its network."
        dataTestId="tobogganing-no-connection"
      />
    );
  }

  return (
    <div data-testid="tobogganing-screen">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">{title}</h1>
        <p className="text-slate-400 text-sm mt-1">{description}</p>
      </header>
      {children}
    </div>
  );
}

import type { ReactNode } from "react";
import { ProductScreen } from "../../../components/kit";

interface GoughScreenProps {
  title: string;
  description: string;
  productId: number | undefined;
  isConnectionLoading: boolean;
  children: ReactNode;
}

/**
 * Gough's instance of the shared `ProductScreen` shell: flag gate, then
 * connection gate, then header, then content. The gating behaviour itself —
 * what each gate checks, the copy, the generated `gough-*` test ids — lives
 * in `ProductScreen`; this wrapper supplies only Gough's product identity.
 *
 * The flag is checked client-side for navigation only. It is not the
 * security control: the portal refuses a proxy call for a connection the
 * tenant does not own regardless of what the browser believes, and
 * `products:gough:*` scopes are only minted for tenants actually connected
 * to Gough.
 */
export function GoughScreen(props: GoughScreenProps) {
  return (
    <ProductScreen
      productType="gough"
      productLabel="Gough"
      noConnectionReason="manage its fleet."
      {...props}
    />
  );
}

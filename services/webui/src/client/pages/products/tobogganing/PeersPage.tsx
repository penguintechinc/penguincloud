import { DataTable, EmptyState } from "../../../components/kit";
import { TobogganingScreen } from "./TobogganingScreen";
import { peerColumns } from "./peerColumns";
import { useTobogganingPeers } from "./useTobogganing";
import type { TobogganingPeerRow } from "./types";

/**
 * WireGuard peers on this tenant's SD-WAN fabric.
 *
 * **This is `/api/v1/sdwan/wireguard/peers`, not `/api/v1/wireguard/peers`.**
 * The two are one path segment apart and the flat one is Tobogganing's machine
 * control plane: `@require_machine_jwt("wireguard:read")` rejects any token
 * whose `aud` is not `"headend"`, and a portal connection credential carries
 * `aud=="tobogganing"`. That is an audience mismatch rather than a scope one —
 * the wildcard scopes the product already grants would satisfy the scope check,
 * but it never runs. The confusable pair is asserted on both sides
 * (`api/__tests__/tobogganing.test.ts` and `test_tobogganing_webui_paths.py`).
 *
 * No detail drawer and no delete verb. A peer here is three fields — the
 * drawer would restate the row — and revocation
 * (`POST /sdwan/wireguard/keys` and the revoke path) is a key-minting surface
 * that is not allowlisted, so there is nothing to call.
 */
export default function PeersPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useTobogganingPeers();

  // A peer has NO `id` field — it is identified by `node_id`. Keying the table
  // on a missing `id` would collapse every row onto one React key and render a
  // single peer no matter how many the fabric has.
  const rows: TobogganingPeerRow[] = (data ?? []).map((peer) => ({
    ...peer,
    id: String(peer.node_id),
  }));

  return (
    <TobogganingScreen
      title="WireGuard Peers"
      description="Peers holding a WireGuard key on this tenant's fabric."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      {/* Rendered only once the fetch has settled. A count shown while the
          query is in flight reads as "0 peers" — a fact, stated wrongly. */}
      {!isLoading && !error && (
        <p
          className="mb-4 text-sm text-slate-400"
          data-testid="tobogganing-peer-count"
        >
          {rows.length} {rows.length === 1 ? "peer" : "peers"}
        </p>
      )}

      <DataTable<TobogganingPeerRow>
        columns={peerColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Tobogganing WireGuard peers"
      />

      {!isLoading && !error && rows.length === 0 && (
        <EmptyState
          title="No peers hold a key"
          description="Peers appear here once a node has been issued WireGuard keys. Key issuance is not available from the portal."
          dataTestId="tobogganing-peers-empty"
        />
      )}
    </TobogganingScreen>
  );
}

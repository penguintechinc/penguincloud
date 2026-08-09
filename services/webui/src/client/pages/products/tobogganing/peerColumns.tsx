import type { ColumnConfig } from "../../../components/kit";
import { optionalCell } from "./clientColumns";
import type { TobogganingPeerRow } from "./types";

/**
 * Columns for the WireGuard peer table.
 *
 * Three fields, because three is all the product returns
 * (`wireguard_manager.py:135-142`). There is no status, no last-handshake and
 * no transfer counter on this route; inventing a "Status: unknown" column
 * would imply the portal asked and was not told.
 *
 * `public_key` is safe to display — it is the PUBLIC half of the keypair and
 * is what identifies a peer in every WireGuard config. The private key is
 * never returned by this route, is not in `TobogganingPeer`, and must not be
 * added: `POST /sdwan/wireguard/keys` mints one and is not allowlisted.
 *
 * The key is rendered in a monospace cell and allowed to wrap rather than
 * truncated. A silently shortened base64 key is worse than a long one — an
 * operator comparing it against a node's config would read a match that is not
 * there.
 */
export const peerColumns: ColumnConfig<TobogganingPeerRow>[] = [
  { key: "node_id", label: "Node", render: optionalCell },
  {
    key: "public_key",
    label: "Public key",
    sortable: false,
    render: (value) =>
      value ? (
        <span className="font-mono text-xs break-all">{String(value)}</span>
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
  { key: "ip_address", label: "Tunnel IP", render: optionalCell },
];

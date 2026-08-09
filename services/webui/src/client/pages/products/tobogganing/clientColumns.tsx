import type { ColumnConfig } from "../../../components/kit";
import type { TobogganingClient } from "./types";

const absent = <span className="text-slate-500">—</span>;

const STATUS_STYLES: Record<string, string> = {
  active: "text-emerald-400",
  connected: "text-emerald-400",
  degraded: "text-amber-400",
  offline: "text-red-400",
  revoked: "text-red-400",
  pending: "text-sky-400",
};

/** Colour a lifecycle value without inventing one for an unknown state. */
export function statusCell(value: unknown) {
  if (value === null || value === undefined || value === "") return absent;
  const text = String(value);
  return (
    <span className={STATUS_STYLES[text.toLowerCase()] ?? "text-slate-300"}>
      {text}
    </span>
  );
}

/** Render an optional scalar, dash when the product reported none. */
export function optionalCell(value: unknown) {
  return value === null || value === undefined || value === ""
    ? absent
    : String(value);
}

/**
 * Columns for the SD-WAN client table.
 *
 * `cluster_id` is shown and is allowed to be absent: an enrolled client is not
 * yet assigned to a cluster, and that unassigned state is a thing an operator
 * opens this page to find. Rendering it as blank would read as a layout fault
 * instead.
 *
 * There is no key or credential column. `POST /sdwan/clients` and the
 * rotate-key route mint an `api_key` and are refused by the proxy allowlist
 * outright, so nothing here can display one — and the list route does not
 * return one either.
 */
export const clientColumns: ColumnConfig<TobogganingClient>[] = [
  { key: "name", label: "Name", render: optionalCell },
  { key: "status", label: "Status", render: statusCell },
  { key: "type", label: "Type", render: optionalCell },
  { key: "cluster_id", label: "Cluster", render: optionalCell },
  { key: "last_seen", label: "Last seen", render: optionalCell },
];

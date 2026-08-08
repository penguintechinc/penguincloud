import type { ColumnConfig } from "../../../components/kit";
import type { GoughAgent } from "./types";

const absent = <span className="text-slate-500">—</span>;

/** Status colours for an agent's reported lifecycle. */
const STATUS_CLASSES: Record<string, string> = {
  active: "text-emerald-400",
  suspended: "text-red-400",
  pending: "text-amber-400",
};

/**
 * Columns for the access-agent table.
 *
 * `last_heartbeat` is shown because an agent whose status is `active` but
 * whose heartbeat is hours old is the case an operator is looking for — the
 * status field alone reports what the agent last claimed, not whether it is
 * still there.
 */
export const agentColumns: ColumnConfig<GoughAgent>[] = [
  {
    key: "hostname",
    label: "Hostname",
    render: (value, row) => String(value || row.agent_id || row.id),
  },
  {
    key: "status",
    label: "Status",
    render: (value) => {
      if (!value) return absent;
      const text = String(value);
      return (
        <span className={STATUS_CLASSES[text] ?? "text-slate-300"}>{text}</span>
      );
    },
  },
  {
    key: "ip_address",
    label: "IP address",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "last_heartbeat",
    label: "Last heartbeat",
    render: (value) => (value ? String(value) : absent),
  },
];

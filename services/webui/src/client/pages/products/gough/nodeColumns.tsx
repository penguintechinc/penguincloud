import type { ColumnConfig } from "../../../components/kit";
import type { GoughNode } from "./types";

/** Muted dash for an absent value — an empty cell reads as a layout bug. */
const absent = <span className="text-slate-500">—</span>;

/**
 * Columns for the node fleet table.
 *
 * `state` and `posture` are BOTH shown, and that is deliberate rather than
 * redundant: they answer different questions ("where is this node in
 * provisioning" vs "is it compliant"), and a node can be `ready` while
 * non-compliant. Collapsing them into one status column loses exactly the
 * case an operator is scanning the list for.
 *
 * There is no node `status` field to render — Gough does not have one. See
 * `types.ts`.
 */
export const nodeColumns: ColumnConfig<GoughNode>[] = [
  { key: "name", label: "Name" },
  {
    key: "state",
    label: "State",
    render: (value) =>
      value ? <span className="text-amber-400">{String(value)}</span> : absent,
  },
  {
    key: "posture",
    label: "Posture",
    render: (value) =>
      value ? (
        <span
          className={
            String(value) === "compliant" ? "text-emerald-400" : "text-red-400"
          }
        >
          {String(value)}
        </span>
      ) : (
        absent
      ),
  },
  {
    key: "ipv4",
    label: "IPv4",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "hardware_tags",
    label: "Tags",
    sortable: false,
    render: (value) => {
      const tags = Array.isArray(value) ? (value as string[]) : [];
      if (tags.length === 0) return absent;
      return (
        <span className="flex flex-wrap gap-1">
          {tags.map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded bg-slate-700 text-xs text-slate-300"
            >
              {tag}
            </span>
          ))}
        </span>
      );
    },
  },
];

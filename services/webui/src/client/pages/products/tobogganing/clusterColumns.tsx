import type { ColumnConfig } from "../../../components/kit";
import { optionalCell, statusCell } from "./clientColumns";
import type { TobogganingCluster } from "./types";

/**
 * Columns for the SD-WAN cluster table.
 *
 * `client_count` is reported by the product, not derived from the clients
 * screen. Counting the rows of `GET /sdwan/clients` here would give a
 * different number for a legitimate reason — that list is the clients this
 * tenant can see, while the count is what the cluster manager holds — and two
 * screens disagreeing about "how many clients" is worse than one number an
 * operator can attribute.
 *
 * Zero is rendered as zero, not as a dash: `optionalCell` would turn a real
 * count of 0 into "the product did not report one", which is a different and
 * false statement. An empty cluster is exactly what an operator is looking for
 * when a rollout has not landed.
 */
export const clusterColumns: ColumnConfig<TobogganingCluster>[] = [
  { key: "name", label: "Name", render: optionalCell },
  { key: "status", label: "Status", render: statusCell },
  { key: "region", label: "Region", render: optionalCell },
  { key: "datacenter", label: "Datacenter", render: optionalCell },
  {
    key: "client_count",
    label: "Clients",
    render: (value) =>
      typeof value === "number" ? (
        String(value)
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
];

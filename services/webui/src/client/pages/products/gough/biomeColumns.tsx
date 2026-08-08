import type { FormField } from "@penguintechinc/react-libs";
import type { ColumnConfig } from "../../../components/kit";
import type { GoughBiome } from "./types";

const absent = <span className="text-slate-500">—</span>;

/**
 * Columns for the biome (deployable workload definition) table.
 *
 * Biomes carry no lifecycle status; `is_active` is the closest thing and is
 * rendered as active/inactive so the column means something. Leaving it blank
 * would make every biome look stateless in a list an operator reads alongside
 * the node fleet.
 */
export const biomeColumns: ColumnConfig<GoughBiome>[] = [
  { key: "name", label: "Name" },
  {
    key: "is_active",
    label: "Active",
    render: (value) =>
      value == null ? (
        absent
      ) : (
        <span className={value ? "text-emerald-400" : "text-slate-400"}>
          {value ? "active" : "inactive"}
        </span>
      ),
  },
  {
    key: "biome_kind",
    label: "Kind",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "workload_type",
    label: "Workload",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "version",
    label: "Version",
    render: (value) => (value ? String(value) : absent),
  },
];

/**
 * Create/edit form fields.
 *
 * Restricted to the fields Gough's create handler accepts and an operator can
 * meaningfully set from a portal. The hardware-tag and signing fields are
 * deliberately absent: they are cluster-policy concerns that Gough's own
 * console owns, and a half-populated tag list here silently changes
 * scheduling.
 */
export const biomeFields: FormField[] = [
  { name: "name", label: "Name", type: "text", required: true },
  {
    name: "biome_kind",
    label: "Kind",
    type: "select",
    defaultValue: "custom",
    // k8s and storage biomes need gough.cluster.admin on Gough's side to
    // upgrade. They are offered because creating one is legitimate, but an
    // operator who cannot upgrade them will see Gough refuse that later.
    options: [
      { value: "custom", label: "Custom" },
      { value: "k8s", label: "Kubernetes" },
      { value: "storage", label: "Storage" },
    ],
  },
  {
    name: "workload_type",
    label: "Workload type",
    type: "select",
    defaultValue: "lxc",
    options: [
      { value: "lxc", label: "LXC" },
      { value: "vm", label: "VM" },
    ],
  },
  { name: "version", label: "Version", type: "text" },
];

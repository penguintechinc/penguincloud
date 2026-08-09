import type { FormField } from "@penguintechinc/react-libs";
import type { ColumnConfig } from "../../../components/kit";
import type { NestDatabaseRow } from "./types";

const absent = <span className="text-slate-500">—</span>;

const PHASE_STYLES: Record<string, string> = {
  Ready: "text-emerald-400",
  Failed: "text-red-400",
  Pending: "text-amber-400",
  Provisioning: "text-sky-400",
};

/**
 * Columns for the data-resource (Database) table.
 *
 * `phase` and `healthState` are BOTH shown because they answer different
 * questions: a resource can be `Ready` (provisioning finished) and unhealthy
 * (its last probe failed). Collapsing them into one "status" column would hide
 * exactly the case an operator opens this page to find.
 *
 * `importConnStr` is not here and is not in `NestDatabase` either — it is a
 * connection string for an imported resource and can carry credentials.
 */
export const databaseColumns: ColumnConfig<NestDatabaseRow>[] = [
  { key: "name", label: "Name" },
  {
    key: "phase",
    label: "Phase",
    render: (value) =>
      value ? (
        <span className={PHASE_STYLES[String(value)] ?? "text-slate-300"}>
          {String(value)}
        </span>
      ) : (
        absent
      ),
  },
  {
    key: "healthState",
    label: "Health",
    render: (value) =>
      value ? (
        <span
          className={
            String(value).toLowerCase() === "healthy"
              ? "text-emerald-400"
              : "text-red-400"
          }
        >
          {String(value)}
        </span>
      ) : (
        absent
      ),
  },
  {
    key: "resourceType",
    label: "Type",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "storageClass",
    label: "Storage class",
    render: (value) => (value ? String(value) : absent),
  },
  {
    key: "sizeGi",
    label: "Size",
    render: (value) =>
      value === null || value === undefined ? absent : `${String(value)} GiB`,
  },
];

/**
 * Create-form fields.
 *
 * The portal-facing names `resourceType` and `storageClass` are used
 * deliberately. Nest's create handler READS `type`/`class` while its serialiser
 * EMITS `resourceType`/`storageClass`, so a form posting what it just read gets
 * `400 nest.dataresource.invalid`. The adapter's `CREATE_FIELD_ALIASES`
 * normalises one into the other; sending the portal names is what exercises
 * that path rather than depending on the operator to know the asymmetry.
 *
 * The type list is Nest's own `valid_types` set (`handlers/dataresource.py`) —
 * anything outside it is rejected with `nest.dataresource.invalid_type`, so
 * offering a free-text field here would just move the error later.
 */
export const databaseFields: FormField[] = [
  { name: "name", label: "Name", type: "text", required: true },
  {
    name: "resourceType",
    label: "Resource type",
    type: "select",
    required: true,
    defaultValue: "postgres",
    options: [
      { value: "postgres", label: "PostgreSQL" },
      { value: "keyvalue", label: "Key/value" },
      { value: "search", label: "Search" },
      { value: "object", label: "Object store" },
      { value: "pvc/block", label: "Block volume" },
      { value: "pvc/file", label: "File volume" },
      { value: "nfs", label: "NFS" },
      { value: "iscsi", label: "iSCSI" },
    ],
  },
  { name: "storageClass", label: "Storage class", type: "text" },
  {
    name: "namespace",
    label: "Namespace",
    type: "text",
    defaultValue: "default",
  },
];

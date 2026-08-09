import type { FormField } from "@penguintechinc/react-libs";
import type { ColumnConfig } from "../../../components/kit";
import { optionalCell } from "./clientColumns";
import type { TobogganingSwgPolicy } from "./types";

/**
 * The product's enforcement actions, in its own severity order.
 *
 * `allow < log_only < soft_block < block < drop`
 * (`hub_api/modules/sase/security/enforcement.py:15-24`). The order is not
 * cosmetic: when several policies match at the same scope, Tobogganing applies
 * the MOST RESTRICTIVE of them, so an operator adding `allow` beside an
 * existing `block` does not get `allow`. Listing them in severity order is the
 * cheapest way to make that visible at the point of choosing.
 *
 * `isolate` is commented out in the product as "reserved — not implemented",
 * so it is not offered here.
 */
export const SWG_ACTIONS = [
  { value: "allow", label: "Allow" },
  { value: "log_only", label: "Log only" },
  { value: "soft_block", label: "Soft block" },
  { value: "block", label: "Block" },
  { value: "drop", label: "Drop" },
] as const;

const ACTION_STYLES: Record<string, string> = {
  allow: "text-emerald-400",
  log_only: "text-sky-400",
  soft_block: "text-amber-400",
  block: "text-red-400",
  drop: "text-red-500",
};

/** Scope precedence, most specific first — `user > group > tenant`. */
export const SWG_SCOPES = [
  { value: "tenant", label: "Whole tenant" },
  { value: "group", label: "Group" },
  { value: "user", label: "User" },
] as const;

/**
 * Columns for the SWG category-policy table.
 *
 * `scope_id` is null for a tenant-wide policy, and that is rendered as
 * "Everyone" rather than as a dash. A dash would say "the product did not
 * report one", when in fact a tenant-scoped policy has no subject BY
 * DEFINITION and applies to every user — the opposite reading, and the more
 * consequential one to get wrong.
 */
export const swgPolicyColumns: ColumnConfig<TobogganingSwgPolicy>[] = [
  { key: "category", label: "Category", render: optionalCell },
  {
    key: "action",
    label: "Action",
    render: (value) =>
      value ? (
        <span
          className={
            ACTION_STYLES[String(value).toLowerCase()] ?? "text-slate-300"
          }
        >
          {String(value)}
        </span>
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
  { key: "scope", label: "Scope", render: optionalCell },
  {
    key: "scope_id",
    label: "Applies to",
    render: (value, row) =>
      value ? (
        String(value)
      ) : row.scope === "tenant" ? (
        <span className="text-slate-300">Everyone</span>
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
];

/**
 * The set-policy form.
 *
 * No `tenant` field: the product derives it from the JWT and rejects a body
 * tenant that disagrees, so offering one could only ever produce a 403.
 *
 * `scope_id` is shown only for group and user scopes — a tenant policy has no
 * subject, and a filled-in id there would be silently ignored.
 */
export const swgPolicyFields: FormField[] = [
  {
    name: "scope",
    label: "Scope",
    type: "select",
    required: true,
    defaultValue: "tenant",
    options: SWG_SCOPES.map((scope) => ({ ...scope })),
    helpText:
      "Precedence is user, then group, then tenant — the most specific match wins.",
  },
  {
    name: "scope_id",
    label: "Group or user id",
    type: "text",
    showWhen: (values) => values.scope === "group" || values.scope === "user",
  },
  { name: "category", label: "Category", type: "text", required: true },
  {
    name: "action",
    label: "Action",
    type: "select",
    required: true,
    defaultValue: "block",
    options: SWG_ACTIONS.map((action) => ({ ...action })),
    helpText:
      "When several policies match at one scope, the most restrictive applies.",
  },
];

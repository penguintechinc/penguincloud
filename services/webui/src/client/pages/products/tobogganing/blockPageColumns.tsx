import type { FormField } from "@penguintechinc/react-libs";
import type { ColumnConfig } from "../../../components/kit";
import { optionalCell } from "./clientColumns";
import type { TobogganingBlockPage } from "./types";

/** Draft vs published is the distinction the whole screen turns on. */
const STATUS_STYLES: Record<string, string> = {
  published: "text-emerald-400",
  draft: "text-amber-400",
  archived: "text-slate-400",
};

/**
 * Columns for the block-page table.
 *
 * `status` is a DRAFT/PUBLISHED lifecycle, not health — it answers "do blocked
 * users see this yet". It is styled distinctly from the SD-WAN status columns
 * for that reason: reusing `statusCell` there would colour "published" with
 * the same green that means "this client is connected", conflating two
 * unrelated vocabularies.
 *
 * `markdown` is deliberately not a column. It is the full page source, and a
 * table cell would either truncate it into something misleading or wreck the
 * row height. It lives in the drawer, where it can be read whole.
 */
export const blockPageColumns: ColumnConfig<TobogganingBlockPage>[] = [
  { key: "name", label: "Name", render: optionalCell },
  {
    key: "status",
    label: "Status",
    render: (value) =>
      value ? (
        <span
          className={
            STATUS_STYLES[String(value).toLowerCase()] ?? "text-slate-300"
          }
        >
          {String(value)}
        </span>
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
  {
    key: "version",
    label: "Version",
    render: (value) =>
      typeof value === "number" ? (
        String(value)
      ) : (
        <span className="text-slate-500">—</span>
      ),
  },
  { key: "updated_by", label: "Updated by", render: optionalCell },
  { key: "updated_at", label: "Updated", render: optionalCell },
];

/**
 * Create-form fields.
 *
 * `name` and `markdown` are the only two the product's create handler reads,
 * and both are rejected when blank (`api.py:165-166`). Offering a `status`
 * field would imply a page can be created published; it cannot — creation
 * always yields a draft, and publishing is a separate guarded verb.
 */
export const blockPageFields: FormField[] = [
  { name: "name", label: "Name", type: "text", required: true },
  {
    name: "markdown",
    label: "Markdown",
    type: "textarea",
    required: true,
    rows: 12,
    helpText:
      "Rendered for users who hit a block. Placeholders such as {{blocked_url}}, {{category}} and {{reason}} are substituted at render time.",
  },
];

/** Edit form. Name is absent because the product's update route ignores it. */
export const blockPageEditFields: FormField[] = [
  {
    name: "markdown",
    label: "Markdown",
    type: "textarea",
    required: true,
    rows: 12,
    helpText:
      "Editing a published page creates a new version; it does not take effect until published again.",
  },
];

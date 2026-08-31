/**
 * TypeScript mirror of the backend's console-manifest schema
 * (`services/portal-api/app/adapters/manifest.py`, Phase 8 Design §3).
 *
 * Why hand-written rather than read off `api/schema.d.ts`
 * =========================================================
 * `npm run generate:api` already produces a `ConsoleManifest` family from
 * `openapi/v1.yaml` (see `components["schemas"]["ConsoleManifest"]` there),
 * and that generated type is NOT wrong — but it cannot give the manifest
 * renderer the one thing it needs most: `CellSpec.kind` is generated as
 * plain `string`, because quart-schema does not emit a Python `str` field as
 * a JSON Schema enum. A `Record<CellKind, Renderer>` cell registry built
 * against that type could not catch a missing renderer at compile time —
 * exactly the "renders blank" failure Design §3.4 exists to prevent. This
 * file re-derives the handful of fields the backend's OWN `__post_init__`
 * validates as a closed set (`CellSpec.kind`, `ResourceDescriptor.transport`,
 * `ListSpec.pagination`, `ActionSpec`/`DeleteSpec.requires`,
 * `ExtensionSlot.slot`) as real TS unions, and leaves every field the
 * backend itself leaves open (`ActionSpec.variant`, `FormField.field_type`)
 * as `string` — this mirror is exactly as strict as the dataclasses it
 * copies, never stricter.
 *
 * `CELL_KINDS` is the one set this module does not trust to stay in sync by
 * hand: `__tests__/manifestTypes.contract.test.ts` reads
 * `app/adapters/manifest.py`'s `CELL_KINDS` frozenset as TEXT (the same
 * technique `tests/api/test_webui_portal_paths.py` already uses in the other
 * direction — parsing the sibling language's source rather than executing
 * it) and fails if the two sets disagree.
 *
 * Field names, required-ness and nesting below are hand-verified against
 * `openapi/v1.yaml`'s generated schema (regenerate via `npm run
 * generate:api` — see `api/schema.d.ts`), not merely assumed.
 */

/** The CLOSED set of cell kinds this schema version recognises — mirrors
 * `CELL_KINDS` in `app/adapters/manifest.py`. An unrecognised wire value
 * must fall back to `"text"` and log once, never render blank — see
 * `manifestCells.tsx`. */
export const CELL_KINDS = [
  "text",
  "enum_badge",
  "tags",
  "number",
  "bytes",
  "money",
  "timestamp",
  "boolean",
  "link",
  "count",
] as const;

export type CellKind = (typeof CELL_KINDS)[number];

const CELL_KIND_SET: ReadonlySet<string> = new Set(CELL_KINDS);

/** Type guard narrowing a wire `kind` string to the closed {@link CellKind} union. */
export function isCellKind(value: string): value is CellKind {
  return CELL_KIND_SET.has(value);
}

/** One `enum_badge` value -> style-name mapping. */
export interface EnumStyle {
  value: string;
  style: string;
}

/** Display text for a `boolean` cell's two states. */
export interface BooleanLabels {
  true_label: string;
  false_label: string;
}

/**
 * How one column's value is rendered.
 *
 * `kind` is deliberately typed as `string`, not {@link CellKind} — this is
 * the WIRE shape, and an unrecognised value must still parse successfully
 * (Design §3.4's "degrade, never crash"). Narrow it with {@link isCellKind}
 * at the point of dispatch, not here.
 */
export interface CellSpec {
  kind: string;
  styles: EnumStyle[];
  unit?: string | null;
  currency_field?: string | null;
  relative: boolean;
  labels?: BooleanLabels | null;
  to_kind?: string | null;
  id_field?: string | null;
}

/**
 * `absent_as` values the backend actually accepts (`_ABSENT_AS_FIXED` plus
 * the `literal:<text>` form) — `ColumnSpec.__post_init__` refuses anything
 * else at manifest-construction time, so this narrowing is backend-enforced,
 * not merely hopeful.
 */
export type AbsentAs = "dash" | "zero" | `literal:${string}`;

/** One column of a resource's list/detail table. */
export interface ColumnSpec {
  field: string;
  label: string;
  cell: CellSpec;
  sortable: boolean;
  /** Required by the backend for every non-`"text"` cell kind. */
  absent_as?: AbsentAs | null;
}

/**
 * Where a resource's collection lives and how it paginates.
 *
 * `path_bytes` starts with `/` (`ListSpec.__post_init__` refuses otherwise)
 * — that leading slash must be stripped before it reaches
 * `proxyRequestUrl`/`proxyApi.request`, which expect the PRODUCT-relative
 * fragment `goughPaths.ts` already spells without one. See
 * `manifestListFetcher.ts`'s module doc for the regression this guards.
 */
export interface ListSpec {
  path_bytes: string;
  envelope_key: string;
  pagination: "offset" | "cursor" | "none";
}

/** Tab layout for a resource's detail view. Empty means a single pane. */
export interface DetailSpec {
  tabs: string[];
}

/** A parent/child edge between two resource kinds in this manifest. */
export interface RelationshipSpec {
  child_kind: string;
  parent_field: string;
}

/**
 * One field of a create form.
 *
 * Named `ManifestFormField`, not `FormField` — `@penguintechinc/react-libs`
 * already exports a component named `FormField`
 * (`components/FormBuilder/FormField.tsx`), and this is DATA, not a
 * component. See the module doc at the bottom of this file for the shape
 * mismatch this finding surfaces against react-libs' real `FieldConfig`.
 */
export interface ManifestFormField {
  name: string;
  label: string;
  field_type: string;
  required: boolean;
  placeholder?: string | null;
  options: string[];
  default?: string | null;
}

/** One portal-facing -> product-facing form field rename. */
export interface FieldAlias {
  portal_name: string;
  product_name: string;
}

/** A create form: its fields, and the rename a create payload needs. */
export interface FormSpec {
  fields: ManifestFormField[];
  submit_label: string;
  field_aliases: FieldAlias[];
}

/** One non-CRUD verb offered on a resource row. */
export interface ActionSpec {
  verb: string;
  label: string;
  variant: string;
  requires: "read" | "manage";
  confirm?: string | null;
  starts_operations: boolean;
  form?: FormSpec | null;
  enabled_when_field?: string | null;
  enabled_when_in: string[];
}

/** Delete affordance for a resource. `confirm` is mandatory copy. */
export interface DeleteSpec {
  confirm: string;
  requires: "read" | "manage";
}

/**
 * One resource kind: its shape, its columns, and how it is reached.
 *
 * `list` is `null` for a resource with no collection endpoint at all. A
 * resource descriptor that DOES declare `list` carries no field this schema
 * version uses to derive an ITEM path for detail/row actions — see the
 * "item-path" finding in the Step 3 report; the renderer must not
 * string-concatenate one.
 */
export interface ResourceDescriptor {
  kind: string;
  label: string;
  plural_label: string;
  id_field: string;
  name_field: string;
  transport: "proxy" | "typed";
  columns: ColumnSpec[];
  empty_state: string;
  error_state: string;
  list?: ListSpec | null;
  detail: DetailSpec;
  actions: ActionSpec[];
  create?: FormSpec | null;
  delete?: DeleteSpec | null;
  relationships: RelationshipSpec[];
}

/** One entry in the product's nav menu. */
export interface NavItem {
  kind: string;
  label: string;
  icon?: string | null;
}

/** The product's nav menu. */
export interface NavSpec {
  items: NavItem[];
}

/** Presence + display config for the product's operations panel. */
export interface OperationsSpec {
  label: string;
  poll_interval_seconds: number;
}

/** Presence + display config for the product's metrics tile. */
export interface MetricsSpec {
  label: string;
}

/** A named escape hatch — never carries code, only a name. */
export interface ExtensionSlot {
  slot: "detail_tab" | "list_header" | "page" | "cell";
  id: string;
  label: string;
  resource?: string | null;
  position: number;
}

/** The complete descriptor for one product's console screens. */
export interface ConsoleManifest {
  manifest_version: number;
  product_type: string;
  display_name: string;
  nav: NavSpec;
  resources: ResourceDescriptor[];
  operations?: OperationsSpec | null;
  metrics?: MetricsSpec | null;
  extensions: ExtensionSlot[];
}

/** One product's overlaid manifest plus the connection it came from. */
export interface ProductManifestEntry {
  product_id: number;
  product_type: string;
  manifest: ConsoleManifest;
}

/** Envelope for `GET /api/v1/console/manifests`. */
export interface ConsoleManifestsResponse {
  manifests: ProductManifestEntry[];
  count: number;
}

/** Look up one resource descriptor by kind, mirroring `ConsoleManifest.resource`. */
export function findResource(
  manifest: ConsoleManifest,
  kind: string,
): ResourceDescriptor | undefined {
  return manifest.resources.find((resource) => resource.kind === kind);
}

/*
 * Schema finding — FormSpec vs react-libs' real FieldConfig
 * ===========================================================
 * `ManifestFormField` above is a faithful mirror of the backend's
 * `FormField` dataclass, which its OWN docstring says was written to
 * "mirror `@penguintechinc/react-libs`' `FormField` shape closely enough to
 * serialise straight into it" — unverified at the time, per that docstring.
 * It does not, on inspection of the installed package
 * (`node_modules/@penguintechinc/react-libs/dist/components/FormBuilder/`):
 *
 * 1. react-libs exports NO data type named `FormField` at all — `FormField`
 *    there is a `React.FC<FormFieldProps>` (a component). The data shape a
 *    caller actually builds is `FieldConfig` (`FormBuilder/types.d.ts`),
 *    consumed as `FormConfig.fields: FieldConfig[]`.
 * 2. `ManifestFormField.field_type: string` is unvalidated free text on the
 *    backend, but `FieldConfig.type: FieldType` is a CLOSED union
 *    (`'text'|'email'|'password'|'number'|'textarea'|'select'|'checkbox'|
 *    'radio'|'date'|'time'|'datetime-local'|'tel'|'url'`). A manifest
 *    author can emit a `field_type` react-libs' own component would reject
 *    at the type level.
 * 3. `ManifestFormField.options: string[]` (bare strings) vs
 *    `FieldConfig.options: SelectOption[]` (`{value, label, disabled?}`
 *    objects) — a real shape mismatch, not just a naming one. Binding a
 *    manifest create-form to `FormBuilder` needs a mapping step
 *    (`options.map(o => ({value: o, label: o}))`) that does not exist
 *    anywhere yet.
 * 4. `default` (backend) vs `defaultValue` (react-libs) — a rename, cheap
 *    but real.
 *
 * None of this blocks list/detail rendering, which is what Step 3 ships.
 * Binding `ResourceDescriptor.create` to a real `FormBuilder` is deferred —
 * see the Step 3 report for the precise follow-up this leaves.
 */

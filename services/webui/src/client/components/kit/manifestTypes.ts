/**
 * TypeScript mirror of the backend's console-manifest schema
 * (`services/portal-api/app/adapters/manifest.py`, Phase 8 Design §3,
 * schema v2).
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
 * validates as a closed set (`CellSpec.kind`, `FormField.field_type`,
 * `ResourceDescriptor.transport`, `ListSpec.pagination`,
 * `ActionSpec`/`DeleteSpec.requires`, `ExtensionSlot.slot`) as real TS
 * unions, and leaves every field the backend itself leaves open
 * (`ActionSpec.variant`) as `string` — this mirror is exactly as strict as
 * the dataclasses it copies, never stricter.
 *
 * `CELL_KINDS` is the one set this module does not trust to stay in sync by
 * hand: `__tests__/manifestTypes.contract.test.ts` reads
 * `app/adapters/manifest.py`'s `CELL_KINDS` frozenset as TEXT (the same
 * technique `tests/api/test_webui_portal_paths.py` already uses in the other
 * direction — parsing the sibling language's source rather than executing
 * it) and fails if the two sets disagree. `FIELD_TYPES` gets the same
 * treatment for the same reason.
 *
 * Field names, required-ness and nesting below are hand-verified against
 * `openapi/v1.yaml`'s generated schema (regenerate via `npm run
 * generate:api` — see `api/schema.d.ts`), not merely assumed.
 *
 * Schema v2 -- FormField now binds to react-libs' REAL FieldConfig
 * ===================================================================
 * Schema v1's `ManifestFormField` was a faithful mirror of the backend's
 * then-current `FormField` dataclass, whose OWN docstring claimed to
 * "mirror `@penguintechinc/react-libs`' `FormField` shape closely enough to
 * serialise straight into it" — unverified at the time, per that docstring,
 * and wrong on inspection of the actually-published package
 * (`@penguintechinc/react-libs@1.3.4`, pinned in `package.json` —
 * `node_modules/@penguintechinc/react-libs/dist/components/FormBuilder/`,
 * confirmed BYTE-EQUAL to the `~/code/penguin-libs` monorepo checkout of the
 * same file at the pinned version):
 *
 * 1. react-libs exports NO data type named `FormField` at all in the
 *    `FormBuilder` family — `FormField` there is a React component
 *    (`React.FC<FormFieldProps>`, `components/FormBuilder/FormField.tsx`).
 *    (A DIFFERENT, unrelated `FormField` data type does exist, exported by
 *    the OLDER `FormModalBuilder` component — see
 *    `manifestFormFields.ts`'s module doc for why this schema binds to
 *    `FormBuilder`/`FieldConfig` instead.) The data shape a caller actually
 *    builds for `FormBuilder` is `FieldConfig`, consumed as
 *    `FormConfig.fields: FieldConfig[]`. This module keeps the name
 *    `ManifestFormField` for the backend-mirrored type — `FormField` would
 *    collide with the real component import.
 * 2. `field_type` is now the closed {@link FieldType} union, byte-exact with
 *    `FieldConfig.type` — a manifest naming a type `FormBuilder` does not
 *    recognise now refuses to load server-side (`FormField.__post_init__`)
 *    instead of parsing fine and rendering blank.
 * 3. `options` is now `SelectOption[]` (`{value, label, disabled?}`),
 *    matching `FieldConfig.options: SelectOption[]` exactly — no more
 *    `options.map(o => ({value: o, label: o}))` synthesis step.
 * 4. `default_value` matches react-libs' own `defaultValue` in meaning (the
 *    rename from schema v1's `default` avoids shadowing the JS keyword).
 *
 * See `manifestFormFields.ts` for the (now near-trivial) `FieldConfig`
 * binding this alignment makes possible.
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

/** The CLOSED set of form field types this schema version recognises —
 * mirrors `FIELD_TYPES` in `app/adapters/manifest.py`, byte-exact with
 * react-libs' own `FieldConfig.type` union (see this module's doc). */
export const FIELD_TYPES = [
  "text",
  "email",
  "password",
  "number",
  "textarea",
  "select",
  "checkbox",
  "radio",
  "date",
  "time",
  "datetime-local",
  "tel",
  "url",
] as const;

export type FieldType = (typeof FIELD_TYPES)[number];

const FIELD_TYPE_SET: ReadonlySet<string> = new Set(FIELD_TYPES);

/** Type guard narrowing a wire `field_type` string to the closed {@link FieldType} union. */
export function isFieldType(value: string): value is FieldType {
  return FIELD_TYPE_SET.has(value);
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
  /**
   * Additional field names to try, in order, when `field` is null — the
   * renderer shows the first non-null of `[field, ...fallback_fields]`,
   * THEN applies `absent_as` if every one of them is null. Mirrors
   * `ColumnSpec.fallback_fields` in `app/adapters/manifest.py`; Gough's
   * `agents` name column sets `("agent_id", "id")`, reproducing
   * `agentColumns.tsx`'s `String(value || row.agent_id || row.id)` chain —
   * see `manifestCells.tsx`'s `resolveFieldValue`.
   */
  fallback_fields?: readonly string[];
}

/**
 * The exact unwrap path from a proxied collection's RAW body to its array —
 * mirrors `EnvelopeSpec` in `app/adapters/manifest.py`. Schema v2 retypes
 * `ListSpec.envelope_key: string` to `ListSpec.envelope: EnvelopeSpec` for
 * exactly the reason that module's docstring gives: a single key cannot
 * express Gough's real wire shapes (`("data", "nodes")` for the enveloped
 * routes vs the bare `("groups",)` for `biome_groups`). See
 * `manifestListFetcher.ts`'s `readManifestEnvelope` for the ordered walk
 * this drives.
 */
export interface EnvelopeSpec {
  keys: string[];
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
  envelope: EnvelopeSpec;
  pagination: "offset" | "cursor" | "none";
}

/**
 * The item-level route for one resource — distinct from `ListSpec`, and
 * never derived from it. Mirrors `ItemPathSpec` in
 * `app/adapters/manifest.py`: `prefix` is the adapter's own item-route base
 * (no trailing slash), and the real item path for one id is always
 * `` `${prefix}/${id}` `` — see `manifestItemPath.ts`'s `buildManifestItemPath`,
 * the one place that concatenation happens. `sample_id` is a
 * backend-only probe value (see the Python docstring); the renderer never
 * reads it.
 */
export interface ItemPathSpec {
  prefix: string;
  sample_id: string;
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

/** One selectable choice for a `select`/`radio` field — mirrors react-libs'
 * own `SelectOption` (`FormBuilder/types.ts`) exactly. */
export interface SelectOption {
  value: string;
  label: string;
  disabled: boolean;
}

/**
 * One field of a create form — binds to react-libs' real `FieldConfig`, not
 * a lookalike. See this module's doc for the schema v1 -> v2 finding.
 *
 * Named `ManifestFormField`, not `FormField` — `@penguintechinc/react-libs`
 * exports both a `FormField` COMPONENT (`FormBuilder` family) and an
 * unrelated `FormField` DATA type (`FormModalBuilder` family); this is
 * neither, so it keeps its own name rather than colliding with either.
 */
export interface ManifestFormField {
  name: string;
  label: string;
  field_type: string;
  required: boolean;
  placeholder?: string | null;
  options: SelectOption[];
  default_value?: string | null;
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
 * `list` is `null` for a resource with no collection endpoint at all.
 * `item_path` is `null` for a resource with no item-level route either
 * (schema v2 — see `ItemPathSpec`'s Python doc for Gough's `clusters`, the
 * case in point). Never derive one from `list.path_bytes` — see
 * `manifestItemPath.ts`.
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
  item_path?: ItemPathSpec | null;
  detail: DetailSpec;
  actions: ActionSpec[];
  create?: FormSpec | null;
  /**
   * The exact parallel of `create` for an update: same `FormSpec`, posted
   * against the existing row instead of a new one. Mirrors
   * `ResourceDescriptor.edit` in `app/adapters/manifest.py`; `null`/absent
   * means this resource has no edit affordance. Gough's `biomes` sets this
   * to the SAME field set as `create` (`BiomesPage.tsx` opens the identical
   * form for "New biome" and "Edit biome") — see `manifestMutations.ts`'s
   * `useUpdateManifestResource`.
   */
  edit?: FormSpec | null;
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

/**
 * Presence + display config for the product's operations panel.
 *
 * Schema v2 adds `cancel_allowed`/`show_logs` — see this field's Python
 * doc (`OperationsSpec` in `app/adapters/manifest.py`) for why schema v1
 * could only ever render a read-only panel and what closes that gap.
 */
export interface OperationsSpec {
  label: string;
  poll_interval_seconds: number;
  cancel_allowed: boolean;
  show_logs: boolean;
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

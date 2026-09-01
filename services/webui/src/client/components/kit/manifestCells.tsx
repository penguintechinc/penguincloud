/**
 * The cell registry — turns a manifest `ColumnSpec` + one row's value into
 * a rendered cell.
 *
 * `CELL_REGISTRY` is a `Record<CellKind, CellRenderer>`, so TypeScript
 * refuses to compile this file if a {@link CellKind} is added to the union
 * in `manifestTypes.ts` without a matching renderer here — that is the
 * "compile-time safety over the CellSpec union" the Step 3 brief asks for.
 * The RUNTIME side of the same rule (Design §3.4: an unrecognised `kind`
 * must fall back to `"text"` and log once, never render blank) lives in
 * {@link renderCell} below, because the wire value is a plain `string`
 * (`manifestTypes.ts`'s own doc explains why) and a manifest served by an
 * OLDER schema version than a NEWER renderer is exactly the case that path
 * exists for.
 */
import type { ReactNode } from "react";
import type { AbsentAs, CellKind, ColumnSpec } from "./manifestTypes";
import { CELL_KINDS, isCellKind } from "./manifestTypes";

/** A row of manifest-described data — field names are the PRODUCT's own raw
 * JSON keys (see `manifestTypes.ts`'s `ColumnSpec` doc), never normalised. */
export type ManifestRow = Record<string, unknown>;

type CellRenderer = (
  value: unknown,
  column: ColumnSpec,
  row: ManifestRow,
) => ReactNode;

/** Muted marker for an absent value — matches the existing hand-written
 * product pages' own convention (`nodeColumns.tsx`'s `absent` constant): an
 * empty cell reads as a layout bug, a dash reads as "checked, nothing here". */
function AbsentMarker({ text = "—" }: { text?: string }) {
  return <span className="text-slate-500">{text}</span>;
}

/**
 * Render the `absent_as` outcome for a column whose value is missing.
 *
 * `absent_as` is required by the backend for every non-`"text"` column
 * (`ColumnSpec.__post_init__`), so by the time a well-formed manifest
 * reaches here it is always one of `"dash"` / `"zero"` / `"literal:<text>"`.
 * `undefined`/`null`/an unrecognised spelling all degrade to the dash — the
 * same "never crash on a value this module did not itself validate"
 * posture the rest of the kit takes with server data.
 */
function renderAbsent(absentAs: AbsentAs | null | undefined): ReactNode {
  if (absentAs === "zero") return <span>0</span>;
  if (absentAs && absentAs.startsWith("literal:")) {
    return <AbsentMarker text={absentAs.slice("literal:".length)} />;
  }
  return <AbsentMarker />;
}

/** Tailwind classes per `EnumStyle.style` name. `style` is unvalidated free
 * text on the backend (`EnumStyle` has no `__post_init__`), so an unknown
 * name degrades to the neutral slate treatment rather than crashing or
 * inventing a colour. */
const ENUM_STYLE_CLASSES: Record<string, string> = {
  success: "bg-emerald-500/10 text-emerald-400",
  warning: "bg-amber-500/10 text-amber-400",
  danger: "bg-red-500/10 text-red-400",
  info: "bg-sky-500/10 text-sky-400",
  neutral: "bg-slate-500/10 text-slate-400",
};

function enumBadgeClasses(style: string | undefined): string {
  return ENUM_STYLE_CLASSES[style ?? "neutral"] ?? ENUM_STYLE_CLASSES.neutral;
}

/** Human-readable byte size, base-1024. `bytes` cell kind. Callers filter
 * out non-finite input before reaching here (see the `bytes` registry
 * entry below), so this has no finiteness check of its own to leave dead. */
function formatBytes(value: number): string {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let size = Math.abs(value);
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const sign = value < 0 ? "-" : "";
  return `${sign}${size.toFixed(size < 10 && unitIndex > 0 ? 1 : 0)} ${units[unitIndex]}`;
}

/** `"2h ago"`-style relative time. Falls back to the raw string for a
 * timestamp this function cannot parse — never blank, never a thrown error
 * from a malformed upstream value. */
function formatRelativeTimestamp(value: string): string {
  const then = Date.parse(value);
  if (Number.isNaN(then)) return value;
  const deltaSeconds = Math.round((Date.now() - then) / 1000);
  const abs = Math.abs(deltaSeconds);
  const suffix = deltaSeconds >= 0 ? "ago" : "from now";
  if (abs < 60) return `${abs}s ${suffix}`;
  if (abs < 3600) return `${Math.round(abs / 60)}m ${suffix}`;
  if (abs < 86400) return `${Math.round(abs / 3600)}h ${suffix}`;
  return `${Math.round(abs / 86400)}d ${suffix}`;
}

function formatAbsoluteTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

/**
 * Every {@link CellKind}, exhaustively. Adding a kind to `CELL_KINDS` in
 * `manifestTypes.ts` without adding an entry here is a TypeScript error.
 */
const CELL_REGISTRY: Record<CellKind, CellRenderer> = {
  text: (value) => String(value),

  enum_badge: (value, column) => {
    const text = String(value);
    const style = column.cell.styles.find((s) => s.value === text)?.style;
    return (
      <span
        className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${enumBadgeClasses(style)}`}
      >
        {text}
      </span>
    );
  },

  // Empty-but-present is ALSO treated as absent, matching the precedent in
  // the hand-written `nodeColumns.tsx` (`tags.length === 0 -> absent`) — an
  // empty comma-list reads as a layout bug the same way a genuinely missing
  // value does, unlike `count` below where zero is a real, reportable fact.
  tags: (value, column) => {
    const tags = Array.isArray(value) ? value.map(String) : [];
    if (tags.length === 0) return renderAbsent(column.absent_as);
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

  number: (value, column) => {
    const unit = column.cell.unit;
    return unit ? `${String(value)} ${unit}` : String(value);
  },

  bytes: (value) => {
    const numeric = typeof value === "number" ? value : Number(value);
    return Number.isFinite(numeric) ? formatBytes(numeric) : String(value);
  },

  money: (value, column, row) => {
    const currency = column.cell.currency_field
      ? row[column.cell.currency_field]
      : undefined;
    const numeric = typeof value === "number" ? value : Number(value);
    const amount = Number.isFinite(numeric)
      ? numeric.toFixed(2)
      : String(value);
    return currency ? `${amount} ${String(currency)}` : amount;
  },

  timestamp: (value, column) => {
    const raw = String(value);
    return column.cell.relative
      ? formatRelativeTimestamp(raw)
      : formatAbsoluteTimestamp(raw);
  },

  boolean: (value, column) => {
    if (value === true) return column.cell.labels?.true_label ?? "True";
    if (value === false) return column.cell.labels?.false_label ?? "False";
    // Neither true nor false reaching here means the upstream value is not
    // actually a boolean — render it rather than silently discarding it.
    return String(value);
  },

  // No safe navigation target yet — see the item-path finding in the Step 3
  // report. Rendered as plain text (the row's own id field), not an `<a>`,
  // so this never links somewhere a future schema version did not commit to.
  link: (value, column, row) => {
    const id = column.cell.id_field ? row[column.cell.id_field] : value;
    return <span className="text-slate-200">{String(id ?? value)}</span>;
  },

  count: (value) => {
    if (Array.isArray(value)) return String(value.length);
    if (typeof value === "number") return String(value);
    return "0";
  },
};

let warnedUnknownKinds: Set<string> | null = null;

/** Logs an unrecognised cell kind exactly once per kind per session — a
 * manifest served by a newer schema version than this renderer must degrade
 * loudly-once, not spam the console on every row. */
function warnUnknownKindOnce(kind: string): void {
  warnedUnknownKinds ??= new Set();
  if (warnedUnknownKinds.has(kind)) return;
  warnedUnknownKinds.add(kind);
  console.error(
    `[manifestCells] Unknown cell kind, falling back to text { kind: "${kind}" }`,
  );
}

/** Exposed for tests only, so a suite can assert "logs once" without relying
 * on module-load ordering between test files. */
export function resetUnknownCellKindWarnings(): void {
  warnedUnknownKinds = null;
}

/**
 * The first non-null of `[column.field, ...column.fallback_fields]` on
 * `row` — `absent_as` only applies once every one of them is null/undefined.
 * Mirrors the backend's `ColumnSpec.fallback_fields` contract exactly:
 * reproduces `agentColumns.tsx`'s `String(value || row.agent_id ||
 * row.id)` chain (null/undefined-based here, not `||`'s falsy-based check —
 * consistent with the rest of this module treating a real `0`/`false`/`""`
 * as a fact to render, never a missing value).
 */
function resolveFieldValue(column: ColumnSpec, row: ManifestRow): unknown {
  for (const field of [column.field, ...(column.fallback_fields ?? [])]) {
    const candidate = row[field];
    if (candidate !== null && candidate !== undefined) return candidate;
  }
  return undefined;
}

/**
 * Render one cell: `row[column.field]` (or its `fallback_fields` chain)
 * through the registry entry for `column.cell.kind`, honouring `absent_as`
 * for a missing value first.
 *
 * Absence is `null`/`undefined` only — a real `0`, `false`, or `[]` is a
 * fact to render, not a missing value (Design §3.3's named example: "a
 * missing billing summary rendered as 0.00"). `tags` additionally treats an
 * empty array as absent, inside its own renderer above, for the reason
 * given there.
 */
export function renderCell(column: ColumnSpec, row: ManifestRow): ReactNode {
  const value = resolveFieldValue(column, row);
  if (value === null || value === undefined) {
    return renderAbsent(column.absent_as);
  }
  const wireKind = column.cell.kind;
  if (!isCellKind(wireKind)) {
    warnUnknownKindOnce(wireKind);
    return CELL_REGISTRY.text(value, column, row);
  }
  return CELL_REGISTRY[wireKind](value, column, row);
}

export { CELL_KINDS };

/**
 * Binds a manifest `FormSpec` to react-libs' REAL `FormBuilder` component.
 *
 * Schema v1 could only ever approximate this — `manifestTypes.ts`'s own
 * module doc (pre-v2) documented four real shape mismatches between the
 * backend's `FormField` and react-libs' actual `FieldConfig`. Schema v2
 * closes every one of them at the SOURCE (`field_type` is now the closed,
 * byte-exact `FieldType` union; `options` is `SelectOption[]`, not bare
 * strings; `default_value` replaces `default`), so this binding is now a
 * straight field-for-field projection — no synthesis, no `options.map(o =>
 * ({value: o, label: o}))` guess.
 *
 * `field_type` still arrives as a `string` on the wire (the same "narrow at
 * the point of dispatch" discipline `manifestCells.tsx` already applies to
 * `CellSpec.kind`) — a manifest served by an OLDER schema build than this
 * renderer degrades to `"text"` rather than handing `FormBuilder` a value
 * outside its own closed union, which it would refuse at the type level.
 */
import { isFieldType } from "./manifestTypes";
import type { FieldAlias, ManifestFormField } from "./manifestTypes";
import type { FieldConfig, SelectOption } from "@penguintechinc/react-libs";

let warnedUnknownFieldTypes: Set<string> | null = null;

/** Logs an unrecognised `field_type` exactly once per type per session —
 * mirrors `manifestCells.tsx`'s `warnUnknownKindOnce`. */
function warnUnknownFieldTypeOnce(fieldType: string, fieldName: string): void {
  warnedUnknownFieldTypes ??= new Set();
  if (warnedUnknownFieldTypes.has(fieldType)) return;
  warnedUnknownFieldTypes.add(fieldType);
  console.error(
    `[manifestFormFields] Unknown field_type, falling back to text { field_type: "${fieldType}", field: "${fieldName}" }`,
  );
}

/** Exposed for tests only, so a suite can assert "logs once" without
 * relying on module-load ordering between test files. */
export function resetUnknownFieldTypeWarnings(): void {
  warnedUnknownFieldTypes = null;
}

/** One manifest `ManifestFormField` -> one react-libs `FieldConfig`. */
export function toFieldConfig(field: ManifestFormField): FieldConfig {
  const type = isFieldType(field.field_type)
    ? field.field_type
    : (warnUnknownFieldTypeOnce(field.field_type, field.name), "text");

  const options: SelectOption[] | undefined =
    field.options.length > 0
      ? field.options.map((option) => ({
          value: option.value,
          label: option.label,
          disabled: option.disabled,
        }))
      : undefined;

  return {
    name: field.name,
    label: field.label,
    type,
    required: field.required,
    placeholder: field.placeholder ?? undefined,
    options,
    defaultValue: field.default_value ?? undefined,
  };
}

/**
 * Renames the portal-facing keys a `FormBuilder` submit produces to the
 * product-facing keys the create handler actually reads — `FormSpec`'s own
 * `field_aliases`, Design §3.3's Nest finding (a create handler that
 * *reads* `type`/`class` but *serialises* `resourceType`/`storageClass`).
 * Returns a NEW object; `values` itself is never mutated.
 */
export function applyFieldAliases(
  values: Record<string, unknown>,
  aliases: readonly FieldAlias[],
): Record<string, unknown> {
  if (aliases.length === 0) return values;
  const renamed: Record<string, unknown> = { ...values };
  for (const alias of aliases) {
    if (!(alias.portal_name in renamed)) continue;
    renamed[alias.product_name] = renamed[alias.portal_name];
    if (alias.product_name !== alias.portal_name) {
      delete renamed[alias.portal_name];
    }
  }
  return renamed;
}

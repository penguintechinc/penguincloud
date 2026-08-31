/**
 * `toFieldConfig`/`applyFieldAliases` — the schema v2 binding to react-libs'
 * REAL `FieldConfig`, and the portal-facing -> product-facing rename a
 * create payload needs.
 */
import {
  applyFieldAliases,
  resetUnknownFieldTypeWarnings,
  toFieldConfig,
} from "../manifestFormFields";
import type { ManifestFormField } from "../manifestTypes";

function field(overrides: Partial<ManifestFormField> = {}): ManifestFormField {
  return {
    name: "name",
    label: "Name",
    field_type: "text",
    required: true,
    placeholder: null,
    options: [],
    default_value: null,
    ...overrides,
  };
}

beforeEach(() => {
  resetUnknownFieldTypeWarnings();
  jest.restoreAllMocks();
});

describe("toFieldConfig", () => {
  it("projects a plain text field field-for-field", () => {
    expect(toFieldConfig(field())).toEqual({
      name: "name",
      label: "Name",
      type: "text",
      required: true,
      placeholder: undefined,
      options: undefined,
      defaultValue: undefined,
    });
  });

  it("carries placeholder and default_value through when set", () => {
    const config = toFieldConfig(
      field({ placeholder: "e.g. web", default_value: "custom" }),
    );
    expect(config.placeholder).toBe("e.g. web");
    expect(config.defaultValue).toBe("custom");
  });

  it("maps select options 1:1 — no more options.map(o => ({value: o, label: o})) synthesis", () => {
    const config = toFieldConfig(
      field({
        name: "biome_kind",
        field_type: "select",
        options: [
          { value: "custom", label: "Custom", disabled: false },
          { value: "k8s", label: "Kubernetes", disabled: true },
        ],
      }),
    );
    expect(config.type).toBe("select");
    expect(config.options).toEqual([
      { value: "custom", label: "Custom", disabled: false },
      { value: "k8s", label: "Kubernetes", disabled: true },
    ]);
  });

  it("degrades an unrecognised field_type to text and logs exactly once per type", () => {
    const errorSpy = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    const first = toFieldConfig(field({ field_type: "file" }));
    const second = toFieldConfig(field({ name: "other", field_type: "file" }));

    expect(first.type).toBe("text");
    expect(second.type).toBe("text");
    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0][0]).toContain("file");
  });
});

describe("applyFieldAliases", () => {
  it("is a no-op when there are no aliases", () => {
    const values = { name: "web" };
    expect(applyFieldAliases(values, [])).toEqual({ name: "web" });
  });

  it("renames a portal-facing key to its product-facing name", () => {
    const values = { type: "custom", version: "1.0" };
    const renamed = applyFieldAliases(values, [
      { portal_name: "type", product_name: "resourceType" },
    ]);
    expect(renamed).toEqual({ resourceType: "custom", version: "1.0" });
    expect(renamed).not.toHaveProperty("type");
  });

  it("never mutates the input object", () => {
    const values = { type: "custom" };
    applyFieldAliases(values, [
      { portal_name: "type", product_name: "resourceType" },
    ]);
    expect(values).toEqual({ type: "custom" });
  });

  it("skips an alias whose portal_name is not present in the submitted values", () => {
    const values = { name: "web" };
    expect(
      applyFieldAliases(values, [
        { portal_name: "missing", product_name: "renamed" },
      ]),
    ).toEqual({ name: "web" });
  });
});

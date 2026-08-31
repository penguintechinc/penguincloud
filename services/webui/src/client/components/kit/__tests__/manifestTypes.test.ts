import { findResource, isCellKind, isFieldType } from "../manifestTypes";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

function resource(kind: string): ResourceDescriptor {
  return {
    kind,
    label: kind,
    plural_label: kind,
    id_field: "id",
    name_field: "name",
    transport: "typed",
    columns: [
      {
        field: "id",
        label: "ID",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
      },
    ],
    empty_state: "empty",
    error_state: "error",
    detail: { tabs: [] },
    actions: [],
    relationships: [],
  };
}

const MANIFEST: ConsoleManifest = {
  manifest_version: 1,
  product_type: "gough",
  display_name: "Gough",
  nav: { items: [] },
  resources: [resource("nodes"), resource("biomes")],
  extensions: [],
};

describe("findResource", () => {
  it("finds a resource by kind", () => {
    expect(findResource(MANIFEST, "biomes")?.kind).toBe("biomes");
  });

  it("returns undefined for an unknown kind", () => {
    expect(findResource(MANIFEST, "agents")).toBeUndefined();
  });
});

describe("isCellKind", () => {
  it("accepts every documented kind", () => {
    for (const kind of [
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
    ]) {
      expect(isCellKind(kind)).toBe(true);
    }
  });

  it("refuses an unrecognised kind", () => {
    expect(isCellKind("sparkline")).toBe(false);
  });
});

describe("isFieldType", () => {
  it("accepts every documented field type, including the hyphenated one", () => {
    for (const type of [
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
    ]) {
      expect(isFieldType(type)).toBe(true);
    }
  });

  it("refuses an unrecognised field type", () => {
    expect(isFieldType("file")).toBe(false);
  });
});

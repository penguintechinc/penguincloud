/**
 * The capability-subset gate proven generically — no product name appears
 * in a single fixture or assertion below, only the manifest fields the
 * decision actually reads (`ConsoleManifest.operations`, `resource.actions`,
 * `resource.create`, `resource.delete`).
 */
import {
  RESOURCE_CAPABILITIES,
  SUPPORTED_CAPABILITIES,
  requiredCapabilities,
  isManifestRoutable,
} from "../manifestCapabilities";
import type { ConsoleManifest, ResourceDescriptor } from "../manifestTypes";

function resource(
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
    kind: "widgets",
    label: "Widget",
    plural_label: "Widgets",
    id_field: "id",
    name_field: "name",
    transport: "proxy",
    columns: [
      {
        field: "id",
        label: "ID",
        sortable: false,
        cell: { kind: "text", styles: [], relative: false },
      },
    ],
    empty_state: "No widgets.",
    error_state: "Unable to load widgets.",
    list: {
      path_bytes: "/api/v1/widgets/",
      envelope: { keys: ["widgets"] },
      pagination: "none",
    },
    item_path: null,
    detail: { tabs: [] },
    actions: [],
    relationships: [],
    ...overrides,
  };
}

function manifest(
  resources: ResourceDescriptor[],
  operations: ConsoleManifest["operations"] = null,
): ConsoleManifest {
  return {
    manifest_version: 2,
    product_type: "synthetic",
    display_name: "Synthetic",
    nav: { items: [] },
    resources,
    operations,
    metrics: null,
    extensions: [],
  };
}

describe("SUPPORTED_CAPABILITIES", () => {
  it("today covers list, operations, actions, create and edit — each proven by an equivalence test against Gough, not merely rendered code", () => {
    expect([...SUPPORTED_CAPABILITIES]).toEqual([
      "list",
      "operations",
      "actions",
      "create",
      "edit",
    ]);
  });

  it("is a subset of every declared capability, so widening it later cannot add an unknown one", () => {
    for (const capability of SUPPORTED_CAPABILITIES) {
      expect(RESOURCE_CAPABILITIES).toContain(capability);
    }
  });
});

describe("requiredCapabilities", () => {
  it("always requires 'list', even for a bare read-only resource", () => {
    const required = requiredCapabilities(manifest([resource()]), resource());
    expect(required).toEqual(new Set(["list"]));
  });

  it("adds 'operations' from the PRODUCT-level manifest field, not a resource field", () => {
    const withOps = manifest([resource()], {
      label: "Ops",
      poll_interval_seconds: 5,
      cancel_allowed: false,
      show_logs: false,
    });
    expect(requiredCapabilities(withOps, resource())).toEqual(
      new Set(["list", "operations"]),
    );
  });

  it("adds 'actions' when the resource declares a non-empty actions tuple", () => {
    const withActions = resource({
      actions: [
        {
          verb: "restart",
          label: "Restart",
          variant: "primary",
          requires: "manage",
          confirm: "Restart?",
          starts_operations: false,
          form: null,
          enabled_when_field: null,
          enabled_when_in: [],
        },
      ],
    });
    expect(requiredCapabilities(manifest([withActions]), withActions)).toEqual(
      new Set(["list", "actions"]),
    );
  });

  it("folds 'delete' into 'actions' — same unproven render path in ManifestResourceDetail", () => {
    const withDelete = resource({
      item_path: { prefix: "/api/v1/widgets", sample_id: "1" },
      delete: { confirm: "Delete this widget?", requires: "manage" },
    });
    expect(requiredCapabilities(manifest([withDelete]), withDelete)).toEqual(
      new Set(["list", "actions"]),
    );
  });

  it("adds 'create' when the resource declares a create form", () => {
    const withCreate = resource({
      create: {
        fields: [],
        submit_label: "Create",
        field_aliases: [],
      },
    });
    expect(requiredCapabilities(manifest([withCreate]), withCreate)).toEqual(
      new Set(["list", "create"]),
    );
  });

  it("adds 'edit' when the resource declares an edit form", () => {
    const withEdit = resource({
      edit: {
        fields: [],
        submit_label: "Save",
        field_aliases: [],
      },
    });
    expect(requiredCapabilities(manifest([withEdit]), withEdit)).toEqual(
      new Set(["list", "edit"]),
    );
  });

  it("unions every declared capability for a resource that declares them all", () => {
    const kitchenSink = resource({
      item_path: { prefix: "/api/v1/widgets", sample_id: "1" },
      actions: [
        {
          verb: "restart",
          label: "Restart",
          variant: "primary",
          requires: "manage",
          confirm: "Restart?",
          starts_operations: false,
          form: null,
          enabled_when_field: null,
          enabled_when_in: [],
        },
      ],
      create: { fields: [], submit_label: "Create", field_aliases: [] },
      edit: { fields: [], submit_label: "Save", field_aliases: [] },
      delete: { confirm: "Delete?", requires: "manage" },
    });
    const withOps = manifest([kitchenSink], {
      label: "Ops",
      poll_interval_seconds: 5,
      cancel_allowed: true,
      show_logs: true,
    });
    expect(requiredCapabilities(withOps, kitchenSink)).toEqual(
      new Set(["list", "operations", "actions", "create", "edit"]),
    );
  });
});

describe("isManifestRoutable", () => {
  it("routes a resource that requires nothing beyond 'list'", () => {
    expect(isManifestRoutable(manifest([resource()]), resource())).toBe(true);
  });

  it("routes a resource whose manifest declares product-level operations — SUPPORTED_CAPABILITIES now covers 'operations'", () => {
    const withOps = manifest([resource()], {
      label: "Ops",
      poll_interval_seconds: 5,
      cancel_allowed: false,
      show_logs: false,
    });
    expect(isManifestRoutable(withOps, resource())).toBe(true);
  });

  it("routes a resource that declares its own actions — SUPPORTED_CAPABILITIES now covers 'actions'", () => {
    const withActions = resource({
      actions: [
        {
          verb: "restart",
          label: "Restart",
          variant: "primary",
          requires: "manage",
          confirm: "Restart?",
          starts_operations: false,
          form: null,
          enabled_when_field: null,
          enabled_when_in: [],
        },
      ],
    });
    expect(isManifestRoutable(manifest([withActions]), withActions)).toBe(true);
  });

  it("routes a resource that declares a create form — SUPPORTED_CAPABILITIES now covers 'create'", () => {
    const withCreate = resource({
      create: { fields: [], submit_label: "Create", field_aliases: [] },
    });
    expect(isManifestRoutable(manifest([withCreate]), withCreate)).toBe(true);
  });

  it("routes a resource that declares an edit form — SUPPORTED_CAPABILITIES now covers 'edit'", () => {
    const withEdit = resource({
      edit: { fields: [], submit_label: "Save", field_aliases: [] },
    });
    expect(isManifestRoutable(manifest([withEdit]), withEdit)).toBe(true);
  });
});

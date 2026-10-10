/**
 * Narrowing helpers for FormBuilder payloads.
 *
 * The load-bearing property is the fallback direction: malformed input must
 * land on the least-privileged value, never widen access.
 */

import {
  formString,
  optionalFormString,
  isUserRole,
  formUserRole,
  isTenantPlan,
  toTenantPlan,
  formBoolean,
} from "../formValues";

describe("formString", () => {
  it("returns a string field", () => {
    expect(formString({ name: "Ada" }, "name")).toBe("Ada");
  });

  it("returns an empty string for a missing key", () => {
    expect(formString({}, "name")).toBe("");
  });

  it("returns an empty string for a non-string value", () => {
    expect(formString({ name: 42 }, "name")).toBe("");
    expect(formString({ name: null }, "name")).toBe("");
  });
});

describe("optionalFormString", () => {
  it("passes a populated value through", () => {
    expect(optionalFormString({ name: "Ada" }, "name")).toBe("Ada");
  });

  it("collapses empty and missing to undefined", () => {
    expect(optionalFormString({ name: "" }, "name")).toBeUndefined();
    expect(optionalFormString({}, "name")).toBeUndefined();
  });
});

describe("isUserRole", () => {
  it.each(["admin", "maintainer", "viewer"])("accepts %s", (role) => {
    expect(isUserRole(role)).toBe(true);
  });

  it.each([["owner"], [""], [null], [undefined], [1], [{}]])(
    "rejects %p",
    (value) => {
      expect(isUserRole(value)).toBe(false);
    },
  );
});

describe("formUserRole", () => {
  it("reads a valid role", () => {
    expect(formUserRole({ role: "admin" }, "role")).toBe("admin");
  });

  it("falls back to viewer on an unknown role", () => {
    expect(formUserRole({ role: "superuser" }, "role")).toBe("viewer");
  });

  it("falls back to viewer when absent", () => {
    expect(formUserRole({}, "role")).toBe("viewer");
  });

  it("honours an explicit fallback", () => {
    expect(formUserRole({}, "role", "maintainer")).toBe("maintainer");
  });
});

describe("isTenantPlan", () => {
  it.each(["free", "starter", "business", "enterprise"])(
    "accepts %s",
    (plan) => {
      expect(isTenantPlan(plan)).toBe(true);
    },
  );

  it.each([["platinum"], [null], [7]])("rejects %p", (value) => {
    expect(isTenantPlan(value)).toBe(false);
  });
});

describe("toTenantPlan", () => {
  it("passes a valid plan through", () => {
    expect(toTenantPlan("enterprise")).toBe("enterprise");
  });

  it("falls back to free on anything unrecognised", () => {
    expect(toTenantPlan("platinum")).toBe("free");
    expect(toTenantPlan(undefined)).toBe("free");
  });

  it("honours an explicit fallback", () => {
    expect(toTenantPlan("platinum", "starter")).toBe("starter");
  });
});

describe("formBoolean", () => {
  it("accepts a real boolean", () => {
    expect(formBoolean({ active: true }, "active")).toBe(true);
    expect(formBoolean({ active: false }, "active")).toBe(false);
  });

  it("accepts the string form a select yields", () => {
    expect(formBoolean({ active: "true" }, "active")).toBe(true);
    expect(formBoolean({ active: "false" }, "active")).toBe(false);
  });

  it("is false for anything else", () => {
    expect(formBoolean({}, "active")).toBe(false);
    expect(formBoolean({ active: 1 }, "active")).toBe(false);
  });
});

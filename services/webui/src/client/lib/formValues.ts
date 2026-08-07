/**
 * Narrowing helpers for FormBuilder submit payloads.
 *
 * FormBuilder hands its `onSubmit` an untyped `Record<string, unknown>`. These
 * helpers read one field at a time with a real runtime check, so form data can
 * reach the typed API clients without an `any` cast or an unguarded assertion
 * silently smuggling the wrong shape through.
 */
import type { TenantPlan, UserRole } from "../types";

const USER_ROLES: readonly UserRole[] = ["admin", "maintainer", "viewer"];

const TENANT_PLANS: readonly TenantPlan[] = [
  "free",
  "starter",
  "business",
  "enterprise",
];

/** Reads a string field, returning "" when absent or not a string. */
export function formString(data: Record<string, unknown>, key: string): string {
  const value = data[key];
  return typeof value === "string" ? value : "";
}

/**
 * Reads an optional string field. Empty and missing both collapse to
 * `undefined` so callers can omit the key from a PATCH-style payload rather
 * than sending an empty string.
 */
export function optionalFormString(
  data: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = formString(data, key);
  return value === "" ? undefined : value;
}

/** Type guard for the UserRole union. */
export function isUserRole(value: unknown): value is UserRole {
  return (
    typeof value === "string" &&
    (USER_ROLES as readonly string[]).includes(value)
  );
}

/**
 * Reads a role field, falling back to the least-privileged role when the value
 * is missing or unrecognised — never widen access on malformed input.
 */
export function formUserRole(
  data: Record<string, unknown>,
  key: string,
  fallback: UserRole = "viewer",
): UserRole {
  const value = data[key];
  return isUserRole(value) ? value : fallback;
}

/** Type guard for the TenantPlan union. */
export function isTenantPlan(value: unknown): value is TenantPlan {
  return (
    typeof value === "string" &&
    (TENANT_PLANS as readonly string[]).includes(value)
  );
}

/**
 * Narrows a select value to TenantPlan, falling back to the least-privileged
 * plan on anything unrecognised.
 */
export function toTenantPlan(
  value: unknown,
  fallback: TenantPlan = "free",
): TenantPlan {
  return isTenantPlan(value) ? value : fallback;
}

/**
 * Reads a boolean field. Select inputs yield the strings "true"/"false", so
 * both the real boolean and its string form are accepted.
 */
export function formBoolean(
  data: Record<string, unknown>,
  key: string,
): boolean {
  const value = data[key];
  return value === true || value === "true";
}

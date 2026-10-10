/**
 * Platform-level endpoints: the sample hello routes, plus the one
 * unauthenticated status endpoint the login page depends on.
 *
 * `goApi` (`/go/status`, `/go/numa/info`, `/go/memory/stats`) was removed
 * rather than repaired. All three resolved to `/api/v1/go/*`, which the portal
 * does not register — and could not have reached the Go backend either, since
 * the webui server rewrites `^/api/go` (`src/server/index.ts:79`), a prefix the
 * axios `baseURL` of `/api/v1` can never produce. Nothing outside its own tests
 * called it, and this repo contains no Go service to check a corrected path
 * against, so guessing one would have been inventing a contract rather than
 * fixing a bug. See task-4N-report.md §Fix round 3.
 */

import api from "../../lib/api";

/** The portal's `RegistrationStatusResponse`, camelCased. */
export interface RegistrationStatus {
  /** Whether `ALLOW_SELF_REGISTRATION` is on for this deployment right now. */
  selfRegistrationEnabled: boolean;
}

/**
 * Decode `GET /api/v1/registration-status`, throwing on anything unexpected.
 *
 * Same "missing key is an error, never a default" rule `decodeFeatures`
 * enforces (`resources/features.ts`): a response this client cannot read is
 * not the same thing as "registration is closed", and conflating the two
 * would make a broken deployment look identical to a deliberate one.
 */
function decodeRegistrationStatus(payload: unknown): RegistrationStatus {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("no registration-status envelope");
  }
  const value = (payload as Record<string, unknown>).self_registration_enabled;
  if (typeof value !== "boolean") {
    throw new Error('"self_registration_enabled" is not a boolean');
  }
  return { selfRegistrationEnabled: value };
}

export const helloApi = {
  get: async (): Promise<{ message: string; timestamp: string }> => {
    const response = await api.get("/hello");
    return response.data;
  },
  getProtected: async (): Promise<{
    message: string;
    user: string;
    role: string;
  }> => {
    const response = await api.get("/hello/protected");
    return response.data;
  },
  /**
   * Unauthenticated: whether this deployment currently allows self-service
   * signup. See `app/hello.py::registration_status` for why this is its own
   * narrow endpoint rather than a field on the authenticated `/features`.
   */
  registrationStatus: async (): Promise<RegistrationStatus> => {
    const response = await api.get("/registration-status");
    return decodeRegistrationStatus(response.data);
  },
};

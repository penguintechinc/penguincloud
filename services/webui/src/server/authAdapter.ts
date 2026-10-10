/**
 * BFF login adapter for the shared-library login page.
 *
 * `LoginPageBuilder` (@penguintechinc/react-libs) issues its own `fetch` and
 * requires a response dialect the portal API does not speak (see
 * `docs/APP_STANDARDS.md` → "Login contract adapter"). This module translates
 * between the two so neither the shared component nor the public API contract
 * has to bend.
 */

/** Raw body posted by LoginPageBuilder. Field types are unverified. */
export interface AdapterRequestBody {
  email?: unknown;
  password?: unknown;
  mfaCode?: unknown;
  rememberMe?: unknown;
  tenant?: unknown;
}

/** Status + JSON body to return to the browser. */
export interface AdapterResult {
  status: number;
  body: Record<string, unknown>;
}

/** Minimal shape of the upstream response this adapter reads. */
interface UpstreamResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

/** The subset of `fetch` the adapter needs, injected so it can be tested. */
export type FetchLike = (
  url: string,
  init: {
    method: string;
    headers: Record<string, string>;
    body: string;
  },
) => Promise<UpstreamResponse>;

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Maps the portal user record onto the library's `LoginResponse["user"]`.
 * Returns undefined when upstream omitted it rather than inventing fields.
 */
function mapUser(raw: unknown): Record<string, unknown> | undefined {
  if (!isRecord(raw)) return undefined;
  const role = typeof raw.role === "string" ? raw.role : undefined;
  return {
    id: String(raw.id ?? ""),
    email: typeof raw.email === "string" ? raw.email : "",
    name: typeof raw.full_name === "string" ? raw.full_name : undefined,
    roles: role ? [role] : [],
  };
}

/**
 * Translates a LoginPageBuilder login attempt into a portal API call.
 *
 * Three shape differences are reconciled here:
 *  1. the library gates on a `success` boolean the API does not send;
 *  2. the library sends `mfaCode`, the API reads `mfa_code`;
 *  3. the API signals "MFA required" with 401 + `mfa_required`, while the
 *     library only reaches its MFA prompt from a 2xx + `mfaRequired` response.
 */
export async function adaptLogin(
  body: AdapterRequestBody,
  upstreamUrl: string,
  fetchImpl: FetchLike,
): Promise<AdapterResult> {
  const email = asNonEmptyString(body.email);
  const password = asNonEmptyString(body.password);

  if (!email || !password) {
    return {
      status: 400,
      body: {
        success: false,
        error: "Email and password are required",
        errorCode: "VALIDATION_ERROR",
      },
    };
  }

  const mfaCode = asNonEmptyString(body.mfaCode);
  const upstreamBody: Record<string, string> = { email, password };
  if (mfaCode) upstreamBody.mfa_code = mfaCode;

  const emailDomain = email.includes("@") ? email.split("@")[1] : "unknown";

  let response: UpstreamResponse;
  try {
    response = await fetchImpl(upstreamUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(upstreamBody),
    });
  } catch {
    console.log(
      `[AuthAdapter] Upstream unreachable { emailDomain: "${emailDomain}" }`,
    );
    return {
      status: 502,
      body: {
        success: false,
        error: "Unable to reach the authentication service",
        errorCode: "UPSTREAM_UNAVAILABLE",
      },
    };
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const payload = isRecord(data) ? data : {};

  if (!response.ok) {
    // The API answers "MFA required" with 401; the library needs a 2xx with
    // `mfaRequired` to open its TOTP prompt instead of failing the attempt.
    if (payload.mfa_required === true) {
      console.log(
        `[AuthAdapter] MFA required { emailDomain: "${emailDomain}" }`,
      );
      return { status: 200, body: { success: true, mfaRequired: true } };
    }

    console.log(
      `[AuthAdapter] Login rejected { emailDomain: "${emailDomain}", status: ${response.status} }`,
    );
    return {
      status: response.status,
      body: {
        success: false,
        error:
          typeof payload.error === "string"
            ? payload.error
            : "Invalid email or password",
        errorCode: "AUTH_FAILED",
      },
    };
  }

  console.log(`[AuthAdapter] Login accepted { emailDomain: "${emailDomain}" }`);
  return {
    status: 200,
    body: {
      success: true,
      token: payload.access_token,
      refreshToken: payload.refresh_token,
      user: mapUser(payload.user),
    },
  };
}

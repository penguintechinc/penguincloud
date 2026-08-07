/**
 * Tests for the BFF login adapter.
 *
 * These also serve as the executable record of WHY the adapter exists: each
 * case below is a shape the portal API emits that LoginPageBuilder cannot
 * consume unmodified.
 */

import { adaptLogin, type FetchLike } from "../authAdapter";

function upstream(status: number, payload: unknown): ReturnType<FetchLike> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  });
}

const PORTAL_LOGIN_OK = {
  access_token: "access-abc",
  refresh_token: "refresh-def",
  token_type: "Bearer",
  expires_in: 3600,
  user: {
    id: 7,
    email: "admin@penguincloud.test",
    full_name: "Ada Admin",
    role: "admin",
  },
};

const URL = "http://api.internal/api/v1/auth/login";

describe("adaptLogin", () => {
  it("adds the success flag the portal API omits", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as FetchLike;

    // The raw upstream body has no `success` key at all — LoginPageBuilder
    // treats `!data.success` as a failed login, which is the incompatibility.
    expect("success" in PORTAL_LOGIN_OK).toBe(false);

    const result = await adaptLogin(
      { email: "admin@penguincloud.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.status).toBe(200);
    expect(result.body.success).toBe(true);
  });

  it("renames the token fields to the library's camelCase contract", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.body.token).toBe("access-abc");
    expect(result.body.refreshToken).toBe("refresh-def");
  });

  it("maps the portal user record onto the library user shape", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.body.user).toEqual({
      id: "7",
      email: "admin@penguincloud.test",
      name: "Ada Admin",
      roles: ["admin"],
    });
  });

  it("omits the user when upstream sends none", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, { access_token: "a", refresh_token: "b" }),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.body.user).toBeUndefined();
  });

  it("translates mfaCode to the snake_case field the API reads", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as jest.Mock;

    await adaptLogin(
      { email: "a@b.test", password: "pw", mfaCode: "123456" },
      URL,
      fetchImpl as unknown as FetchLike,
    );

    const sent = JSON.parse(fetchImpl.mock.calls[0][1].body);
    expect(sent).toEqual({
      email: "a@b.test",
      password: "pw",
      mfa_code: "123456",
    });
  });

  it("omits mfa_code entirely on a first-factor attempt", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as jest.Mock;

    await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl as unknown as FetchLike,
    );

    const sent = JSON.parse(fetchImpl.mock.calls[0][1].body);
    expect("mfa_code" in sent).toBe(false);
  });

  it("turns the API's 401 MFA challenge into a 2xx mfaRequired response", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(401, { error: "MFA code required", mfa_required: true }),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    // LoginPageBuilder only reaches its MFA prompt via `response.ok &&
    // data.success && data.mfaRequired`; a bare 401 would be rendered as a
    // failed login instead.
    expect(result.status).toBe(200);
    expect(result.body).toEqual({ success: true, mfaRequired: true });
  });

  it("passes a genuine credential rejection through with its status", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(401, { error: "Invalid email or password" }),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "nope" },
      URL,
      fetchImpl,
    );

    expect(result.status).toBe(401);
    expect(result.body).toEqual({
      success: false,
      error: "Invalid email or password",
      errorCode: "AUTH_FAILED",
    });
  });

  it("substitutes a generic message when upstream sends no error text", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(403, { detail: "forbidden" }),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.status).toBe(403);
    expect(result.body.error).toBe("Invalid email or password");
  });

  it("tolerates a non-JSON upstream body", async () => {
    const fetchImpl = jest.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("not json")),
      }),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.status).toBe(500);
    expect(result.body.success).toBe(false);
  });

  it("tolerates a non-object JSON upstream body", async () => {
    const fetchImpl = jest.fn(() =>
      upstream(200, "unexpected"),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.body.success).toBe(true);
    expect(result.body.token).toBeUndefined();
  });

  it("returns 502 when the API is unreachable", async () => {
    const fetchImpl = jest.fn(() =>
      Promise.reject(new Error("ECONNREFUSED")),
    ) as unknown as FetchLike;

    const result = await adaptLogin(
      { email: "a@b.test", password: "pw" },
      URL,
      fetchImpl,
    );

    expect(result.status).toBe(502);
    expect(result.body.errorCode).toBe("UPSTREAM_UNAVAILABLE");
  });

  it.each([
    ["missing email", { password: "pw" }],
    ["missing password", { email: "a@b.test" }],
    ["empty email", { email: "", password: "pw" }],
    ["non-string password", { email: "a@b.test", password: 42 }],
  ])("rejects %s without calling upstream", async (_label, body) => {
    const fetchImpl = jest.fn() as unknown as jest.Mock;

    const result = await adaptLogin(
      body,
      URL,
      fetchImpl as unknown as FetchLike,
    );

    expect(result.status).toBe(400);
    expect(result.body.errorCode).toBe("VALIDATION_ERROR");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("never logs the password, token or full email address", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const fetchImpl = jest.fn(() =>
      upstream(200, PORTAL_LOGIN_OK),
    ) as unknown as FetchLike;

    await adaptLogin(
      { email: "secret.person@penguincloud.test", password: "hunter2" },
      URL,
      fetchImpl,
    );

    const logged = logSpy.mock.calls.flat().join(" ");
    expect(logged).not.toContain("hunter2");
    expect(logged).not.toContain("access-abc");
    expect(logged).not.toContain("secret.person@");
    expect(logged).toContain("penguincloud.test");
    logSpy.mockRestore();
  });

  it("handles an email with no domain when logging", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const fetchImpl = jest.fn(() =>
      upstream(401, { error: "nope" }),
    ) as unknown as FetchLike;

    await adaptLogin({ email: "bare", password: "pw" }, URL, fetchImpl);

    expect(logSpy.mock.calls.flat().join(" ")).toContain("unknown");
    logSpy.mockRestore();
  });
});

/**
 * Tests for the BFF session routes: /api/ui/login, /api/ui/refresh and
 * /api/ui/logout.
 *
 * These prove the security fix end-to-end at the HTTP boundary:
 *  - the refresh token is set as an HttpOnly; Secure; SameSite=Strict cookie
 *    scoped to /api/ui and NEVER returned in the login response body;
 *  - refresh is cookie-based and server-side (the browser never sends or
 *    receives a refresh token);
 *  - refresh and logout enforce a double-submit CSRF token;
 *  - logout clears the cookies.
 *
 * As in index.test.ts, `../authAdapter.js` is virtual-mocked (ts-jest does
 * not remap the runtime-required `.js` specifier back to the `.ts` source)
 * and `createApp` is imported rather than `index.ts` (which reads
 * `import.meta`).
 */

import { TextEncoder, TextDecoder } from "util";

if (typeof globalThis.TextEncoder === "undefined") {
  globalThis.TextEncoder =
    TextEncoder as unknown as typeof globalThis.TextEncoder;
  globalThis.TextDecoder =
    TextDecoder as unknown as typeof globalThis.TextDecoder;
}

import request from "supertest";
import type { Express } from "express";

/** Controllable stand-in for the login adapter. */
const adaptLogin = jest.fn();
jest.mock(
  "../authAdapter.js",
  () => ({
    adaptLogin: (...args: unknown[]) => adaptLogin(...args),
  }),
  { virtual: true },
);

import { createApp } from "../app";

const CONFIG = {
  flaskApiUrl: "http://flask.internal",
  goApiUrl: "http://go.internal",
  nodeEnv: "production",
  clientDir: "/nonexistent",
};

/** Finds the Set-Cookie entry for a given cookie name. */
function cookie(
  res: request.Response,
  name: string,
): string | undefined {
  const raw = res.headers["set-cookie"] as unknown as string[] | undefined;
  return (raw ?? []).find((c) => c.startsWith(`${name}=`));
}

let app: Express;

beforeEach(() => {
  jest.clearAllMocks();
  // Node (the real runtime) exposes a global `fetch`; the jsdom test env does
  // not, so the login route's `fetch` reference would throw. The login
  // adapter is mocked and ignores it; refresh tests override this with their
  // own controllable mock.
  global.fetch = jest.fn() as unknown as typeof fetch;
  app = createApp(CONFIG);
});

describe("POST /api/ui/login", () => {
  it("moves the refresh token into an HttpOnly cookie and strips it from the body", async () => {
    adaptLogin.mockResolvedValue({
      status: 200,
      body: {
        success: true,
        token: "access-xyz",
        refreshToken: "refresh-secret",
        user: { id: "1" },
      },
    });

    const res = await request(app)
      .post("/api/ui/login")
      .send({ email: "a@b.test", password: "pw" });

    expect(res.status).toBe(200);
    // Access token still returned for in-memory use.
    expect(res.body.token).toBe("access-xyz");
    // Refresh token NEVER reaches the browser in the body.
    expect(res.body.refreshToken).toBeUndefined();

    const refreshCookie = cookie(res, "pc_refresh");
    expect(refreshCookie).toBeDefined();
    expect(refreshCookie).toContain("pc_refresh=refresh-secret");
    expect(refreshCookie).toContain("HttpOnly");
    expect(refreshCookie).toContain("Secure");
    expect(refreshCookie).toContain("SameSite=Strict");
    expect(refreshCookie).toContain("Path=/api/ui");

    // A readable (non-HttpOnly) CSRF cookie accompanies it for double-submit.
    const csrfCookie = cookie(res, "csrf");
    expect(csrfCookie).toBeDefined();
    expect(csrfCookie).not.toContain("HttpOnly");
    expect(csrfCookie).toContain("SameSite=Strict");
    expect(csrfCookie).toContain("Path=/");
  });

  it("sets no cookie on an MFA challenge", async () => {
    adaptLogin.mockResolvedValue({
      status: 200,
      body: { success: true, mfaRequired: true },
    });

    const res = await request(app)
      .post("/api/ui/login")
      .send({ email: "a@b.test", password: "pw" });

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true, mfaRequired: true });
    expect(cookie(res, "pc_refresh")).toBeUndefined();
  });

  it("sets no cookie on a rejected login", async () => {
    adaptLogin.mockResolvedValue({
      status: 401,
      body: { success: false, error: "Invalid email or password" },
    });

    const res = await request(app)
      .post("/api/ui/login")
      .send({ email: "a@b.test", password: "nope" });

    expect(res.status).toBe(401);
    expect(cookie(res, "pc_refresh")).toBeUndefined();
  });
});

describe("POST /api/ui/refresh", () => {
  const TOKEN = "csrf-token-value";
  const WITH_SESSION = `pc_refresh=refresh-secret; csrf=${TOKEN}`;

  it("rejects a request with no CSRF header (double-submit)", async () => {
    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION);

    expect(res.status).toBe(403);
    expect(res.body.errorCode).toBe("CSRF_FAILED");
  });

  it("rejects a mismatched CSRF header", async () => {
    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION)
      .set("X-CSRF-Token", "not-the-token");

    expect(res.status).toBe(403);
    expect(res.body.errorCode).toBe("CSRF_FAILED");
  });

  it("returns 401 when there is no refresh cookie", async () => {
    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", `csrf=${TOKEN}`)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(401);
    expect(res.body.errorCode).toBe("NO_SESSION");
  });

  it("exchanges the cookie for a fresh access token and rotates the cookie", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "new-access",
        refresh_token: "rotated-refresh",
      }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ access_token: "new-access" });
    // Backend was called server-side with the cookie's refresh token.
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://flask.internal/api/v1/auth/refresh");
    expect(JSON.parse(init.body)).toEqual({ refresh_token: "refresh-secret" });
    // Cookie rotated to the new refresh token, still HttpOnly.
    const refreshCookie = cookie(res, "pc_refresh");
    expect(refreshCookie).toContain("pc_refresh=rotated-refresh");
    expect(refreshCookie).toContain("HttpOnly");
  });

  it("keeps the existing refresh token when the backend does not rotate it", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "new-access" }),
    }) as unknown as typeof fetch;

    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(200);
    expect(cookie(res, "pc_refresh")).toContain("pc_refresh=refresh-secret");
  });

  it("clears the cookies and returns 401 when the backend rejects the refresh token", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: "expired" }),
    }) as unknown as typeof fetch;

    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(401);
    expect(res.body.errorCode).toBe("REFRESH_REJECTED");
    // Cookie cleared (expired) so the client stops retrying.
    const refreshCookie = cookie(res, "pc_refresh");
    expect(refreshCookie).toBeDefined();
    expect(refreshCookie).toMatch(/Expires=Thu, 01 Jan 1970|pc_refresh=;/);
  });

  it("returns 502 when the backend is unreachable", async () => {
    global.fetch = jest
      .fn()
      .mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;

    const res = await request(app)
      .post("/api/ui/refresh")
      .set("Cookie", WITH_SESSION)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(502);
    expect(res.body.errorCode).toBe("UPSTREAM_UNAVAILABLE");
  });
});

describe("POST /api/ui/logout", () => {
  const TOKEN = "csrf-token-value";

  it("rejects without a matching CSRF token", async () => {
    const res = await request(app)
      .post("/api/ui/logout")
      .set("Cookie", `csrf=${TOKEN}`);

    expect(res.status).toBe(403);
    expect(res.body.errorCode).toBe("CSRF_FAILED");
  });

  it("clears the session cookies", async () => {
    const res = await request(app)
      .post("/api/ui/logout")
      .set("Cookie", `pc_refresh=refresh-secret; csrf=${TOKEN}`)
      .set("X-CSRF-Token", TOKEN);

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true });
    expect(cookie(res, "pc_refresh")).toBeDefined();
    expect(cookie(res, "csrf")).toBeDefined();
  });
});

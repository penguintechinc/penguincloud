/**
 * Proves the security headers configured in app.ts actually land on every
 * response shape this origin produces: a JSON route defined in this file, a
 * literal static-file response served via `express.static`, the SPA
 * fallback, and a response proxied from the upstream Flask/Go APIs.
 * `helmet()` is mounted first in the middleware chain, so all of them should
 * carry the same header set.
 *
 * `createApp` (not `index.ts`) is imported here deliberately: `index.ts`
 * calls `fileURLToPath(import.meta.url)` at module scope, and a dynamically
 * `import()`-ed copy of that file gets compiled to CommonJS by ts-jest
 * (verified: it throws "Cannot use 'import.meta' outside a module"), which
 * `app.ts` never touches. `createApp` also takes its config as a plain
 * argument rather than reading `process.env`, so this suite builds two
 * independently-configured app instances without `jest.resetModules()`.
 */

import { TextEncoder, TextDecoder } from "util";

// This suite runs in the repo's shared jsdom test environment (the global
// setupFilesAfterEnv touches `window`, so a per-file `@jest-environment node`
// override breaks it) — but jsdom does not polyfill TextEncoder/TextDecoder,
// which supertest's HTTP client chain requires transitively. Polyfilled
// locally, scoped to this file only, rather than touching the shared jest
// setup that src/client tests also depend on.
// A direct type assertion is used below (rather than a TS suppression
// comment) because whether Node's util.TextEncoder/TextDecoder types
// structurally match the DOM-lib globals jsdom otherwise provides depends on
// which tsconfig is compiling this file: jest's transform includes the
// "dom" lib (a mismatch exists) but tsconfig.server.json's build:server
// pass — which also sweeps up this __tests__ file — does not, so a
// suppression comment would be flagged as unused in one of the two
// contexts no matter which way it's written.
if (typeof globalThis.TextEncoder === "undefined") {
  globalThis.TextEncoder =
    TextEncoder as unknown as typeof globalThis.TextEncoder;
  globalThis.TextDecoder =
    TextDecoder as unknown as typeof globalThis.TextDecoder;
}

import http from "http";
import path from "path";
import type { AddressInfo } from "net";
import request from "supertest";
import type { Express } from "express";

// `app.ts` imports `./authAdapter.js` (the `.js` extension is required for
// the real Node ESM runtime — see app.ts) but only `authAdapter.ts` exists
// on disk, and ts-jest's module resolution does not remap that extension
// back to the `.ts` source. `virtual: true` mocks the specifier without
// requiring it to resolve on disk, scoped to this test file only, rather
// than adding a project-wide `.js`-stripping moduleNameMapper to the shared
// jest.config.js. The adapter's real behavior is unrelated to this suite —
// it has its own dedicated test file (authAdapter.test.ts) — and the login
// route it backs isn't exercised by any test here.
jest.mock("../authAdapter.js", () => ({ adaptLogin: jest.fn() }), {
  virtual: true,
});

import { createApp } from "../app";

describe("security headers", () => {
  let upstream: http.Server;
  let upstreamUrl: string;
  let prodApp: Express;
  let devApp: Express;

  beforeAll(async () => {
    // Stand-in for the Flask/Go upstreams the /api proxy targets. Echoes a
    // trivial JSON body so we only need to assert on headers, not payload.
    upstream = http.createServer((_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ upstream: true }));
    });
    await new Promise<void>((resolve) => upstream.listen(0, resolve));
    const { port } = upstream.address() as AddressInfo;
    upstreamUrl = `http://127.0.0.1:${port}`;

    // `src/client` (not a built `dist/client`) — jest's rootDir/cwd for this
    // package is the webui package root, and src/client is a real directory
    // (containing index.css) that exercises the actual express.static
    // middleware in the same way the built dist/client does at runtime.
    const clientDir = path.resolve(process.cwd(), "src/client");

    prodApp = createApp({
      flaskApiUrl: upstreamUrl,
      goApiUrl: upstreamUrl,
      nodeEnv: "production",
      clientDir,
    });

    devApp = createApp({
      flaskApiUrl: upstreamUrl,
      goApiUrl: upstreamUrl,
      nodeEnv: "development",
      clientDir,
    });
  });

  afterAll(() => {
    upstream.close();
  });

  function expectSecureHeaders(headers: Record<string, string | string[]>) {
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["content-security-policy"]).toContain(
      "frame-ancestors 'none'",
    );
    expect(headers["content-security-policy"]).toContain("object-src 'none'");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["strict-transport-security"]).toMatch(/^max-age=15552000/);
    expect(headers["strict-transport-security"]).not.toContain(
      "includeSubDomains",
    );
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["x-powered-by"]).toBeUndefined();
  }

  it("sets security headers on a JSON route this server owns", async () => {
    const res = await request(devApp).get("/healthz");
    expect(res.status).toBe(200);
    expectSecureHeaders(res.headers);
  });

  it("sets security headers on a literal static-file response", async () => {
    const res = await request(prodApp).get("/index.css");
    expect(res.status).toBe(200);
    expectSecureHeaders(res.headers);
  });

  it("sets security headers on the SPA fallback response", async () => {
    const res = await request(prodApp).get("/some/deep/route");
    // No index.html exists under src/client at test time (it lives at the
    // package root, one level up from clientDir) so this 404s — but the
    // headers are applied by helmet before the route handler ever runs, so
    // they must be present regardless of what the handler does with the
    // request.
    expectSecureHeaders(res.headers);
  });

  it("sets security headers on a proxied /api response", async () => {
    const res = await request(devApp).get("/api/v1/hello");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ upstream: true });
    expectSecureHeaders(res.headers);
  });

  it("sets security headers on a proxied /api/go response", async () => {
    const res = await request(devApp).get("/api/go/hello");
    expect(res.status).toBe(200);
    expectSecureHeaders(res.headers);
  });

  it("scopes 'unsafe-inline' to style-src only, never script-src", async () => {
    const res = await request(devApp).get("/healthz");
    const csp = String(res.headers["content-security-policy"]);
    const scriptSrcDirective = csp
      .split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith("script-src"));
    const styleSrcDirective = csp
      .split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith("style-src"));
    expect(scriptSrcDirective).toBe("script-src 'self'");
    expect(styleSrcDirective).toBe("style-src 'self' 'unsafe-inline'");
  });
});

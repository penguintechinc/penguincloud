import express, { Request, Response, NextFunction } from "express";
import helmet from "helmet";
import { randomBytes, timingSafeEqual } from "node:crypto";
import {
  createProxyMiddleware,
  fixRequestBody,
  Options,
} from "http-proxy-middleware";
import { adaptLogin } from "./authAdapter.js";

/** Runtime configuration `createApp` needs — no direct `process.env` reads
 * inside this module, so tests can construct multiple independently-
 * configured app instances without `jest.resetModules()`. */
export interface AppConfig {
  flaskApiUrl: string;
  goApiUrl: string;
  nodeEnv: string;
  /** Directory containing the built client bundle (`dist/client` at
   * runtime). Only read when `nodeEnv === "production"`. */
  clientDir: string;
}

// ---------------------------------------------------------------------------
// BFF-managed session cookies
// ---------------------------------------------------------------------------
// The refresh token used to be handed to the browser in the login response
// body and persisted in localStorage (both in src/client/lib/api.ts and the
// zustand `auth-storage` partialize). An XSS could read it and mint access
// tokens indefinitely — durable account takeover. It now lives ONLY in an
// HttpOnly cookie the BFF owns; browser JavaScript can never read it, and the
// backend refresh call happens server-side here. The short-lived access token
// is still returned in the JSON body for in-memory use by the client and is
// never persisted anywhere.

/** HttpOnly cookie carrying the refresh token. Scoped to `/api/ui` so it is
 *  sent only to the three BFF session routes below — never to the `/api`
 *  proxy, the static SPA, or any product call. */
const REFRESH_COOKIE = "pc_refresh";

/** Readable (non-HttpOnly) companion cookie for double-submit CSRF defense.
 *  The client echoes it back in the `X-CSRF-Token` header on the
 *  cookie-authenticated POSTs (refresh/logout); a cross-site request cannot
 *  read it, so it cannot forge the header. Not a secret. Path `/` so the
 *  SPA (served at `/`) can read it via `document.cookie`. */
const CSRF_COOKIE = "csrf";
const CSRF_HEADER = "x-csrf-token";

/** The refresh cookie is confined to the session routes. */
const SESSION_COOKIE_PATH = "/api/ui";

/** Parses the `Cookie` request header without pulling in `cookie-parser` —
 *  one small dependency-free reader is all the three session routes need. */
function parseCookies(header: string | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    const name = part.slice(0, eq).trim();
    if (!name) continue;
    out[name] = decodeURIComponent(part.slice(eq + 1).trim());
  }
  return out;
}

/** 256 bits of CSRF entropy, hex-encoded. */
function issueCsrfToken(): string {
  return randomBytes(32).toString("hex");
}

/** Sets (or rotates) the refresh + CSRF cookie pair. Returns the CSRF token
 *  so a caller can hand it back in the body if it ever needs to. `secure` is
 *  true in production — the only environment served over HTTPS; a `Secure`
 *  cookie would be silently dropped by browsers over plain-http localhost
 *  dev, which would make login unusable there. */
function setSessionCookies(
  res: Response,
  refreshToken: string,
  secure: boolean,
): string {
  res.cookie(REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    secure,
    sameSite: "strict",
    path: SESSION_COOKIE_PATH,
  });
  const csrf = issueCsrfToken();
  res.cookie(CSRF_COOKIE, csrf, {
    httpOnly: false,
    secure,
    sameSite: "strict",
    path: "/",
  });
  return csrf;
}

/** Clears both session cookies. Path/attributes must match the ones used to
 *  set them or the browser keeps the cookie. */
function clearSessionCookies(res: Response, secure: boolean): void {
  res.clearCookie(REFRESH_COOKIE, {
    httpOnly: true,
    secure,
    sameSite: "strict",
    path: SESSION_COOKIE_PATH,
  });
  res.clearCookie(CSRF_COOKIE, {
    httpOnly: false,
    secure,
    sameSite: "strict",
    path: "/",
  });
}

/** Constant-time double-submit check: the `X-CSRF-Token` header must equal
 *  the readable `csrf` cookie. SameSite=Strict already blocks the cookie from
 *  riding along on a cross-site request, so this is defense-in-depth on top of
 *  it rather than the sole control. */
function csrfValid(req: Request): boolean {
  const cookieToken = parseCookies(req.headers.cookie)[CSRF_COOKIE];
  const raw = req.headers[CSRF_HEADER];
  const headerToken = Array.isArray(raw) ? raw[0] : raw;
  if (!cookieToken || !headerToken) return false;
  const a = Buffer.from(cookieToken);
  const b = Buffer.from(headerToken);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Builds the Express app: security headers, the BFF login adapter, the
 * Flask/Go API proxies, and (in production) the static SPA bundle. Building
 * this independently of `app.listen()` is what lets the security-headers
 * test suite exercise the real middleware chain via supertest.
 */
export function createApp(config: AppConfig): express.Express {
  const app = express();

  // Cookies set by the session routes carry the `Secure` attribute in
  // production (the only environment served over HTTPS). Over plain-http
  // localhost dev a `Secure` cookie is silently dropped by the browser, which
  // would break login there, so it is relaxed only in that case.
  const secure = config.nodeEnv === "production";

  // Security headers — applied first, before any route or proxy, so every
  // response this origin produces (the SPA shell, its static assets, and the
  // /api proxy responses) carries them. This is the one origin that serves
  // the SPA *and* proxies /api. The refresh token now lives in an HttpOnly
  // cookie this BFF owns (see the session routes below and
  // src/client/lib/api.ts), so an XSS can no longer read it and mint tokens
  // indefinitely; the only token exposed to JavaScript is the short-lived,
  // memory-only access token. CSP is therefore strong defense-in-depth here
  // — it keeps injected script out in the first place — rather than the sole
  // thing standing between an injection and durable account takeover.
  //
  // Secure-by-default: this is unconditional, not opt-in. An operator can
  // only relax it (e.g. a future CSP report-only rollout), never has to turn
  // it on.
  app.use(
    helmet({
      contentSecurityPolicy: {
        directives: {
          // Deny-by-default baseline; every other directive below is an
          // intentional narrowing or a documented, minimal widening.
          defaultSrc: ["'self'"],
          // No 'unsafe-inline'/'unsafe-eval': the production Vite build
          // emits only linked <script type="module" src="..."> files,
          // nothing inline, and nothing in this app calls eval()/new
          // Function().
          scriptSrc: ["'self'"],
          // 'unsafe-inline' is scoped to styles only, never scripts. One
          // legitimate inline style attribute exists today
          // (OperationsPanel.tsx's progress-bar width) and CSS has no
          // script-execution primitive of its own, so this is a narrow,
          // low-severity relaxation — not the same class of risk as inline
          // script.
          styleSrc: ["'self'", "'unsafe-inline'"],
          imgSrc: ["'self'", "data:"],
          fontSrc: ["'self'"],
          // XHR/fetch targets: only this origin's own /api proxy is ever
          // called (see src/client/lib/api.ts and portalPaths.ts) — no
          // third-party API is called directly from the browser.
          connectSrc: ["'self'"],
          // Phase 8 Step 7 deleted `BlockPagePreview.tsx` (the sole reason
          // this was ever 'self' — it rendered operator-authored HTML in a
          // sandbox="" srcDoc iframe, replaced by the manifest console's
          // read-only table). Nothing in this app frames anything anymore,
          // so this tightens to 'none' rather than leaving a widening with
          // no live justification — least privilege, not a defense-in-depth
          // nicety.
          frameSrc: ["'none'"],
          // Nothing here can legitimately be framed by another site.
          frameAncestors: ["'none'"],
          objectSrc: ["'none'"],
          baseUri: ["'self'"],
          formAction: ["'self'"],
          upgradeInsecureRequests: [],
        },
      },
      // HSTS: on by default per secure-by-default. 180 days, applied to
      // this host only. includeSubDomains is deliberately omitted — this
      // app is deployed under shared multi-tenant domains
      // (penguintech.cloud, product .app domains) alongside services this
      // change has no visibility into; forcing HTTPS on sibling subdomains
      // this app doesn't own is a judgment call for whoever controls the
      // zone, not something to assert from inside one service's server.
      // preload is likewise left off: it requires includeSubDomains and is
      // effectively irreversible once submitted.
      hsts: {
        maxAge: 15552000,
        includeSubDomains: false,
        preload: false,
      },
      // frame-ancestors 'none' above is the CSP-native, more capable
      // successor; helmet still sets the legacy X-Frame-Options: DENY
      // header alongside it for browsers that only honor the older header.
      frameguard: { action: "deny" },
      referrerPolicy: { policy: "strict-origin-when-cross-origin" },
      // helmet defaults already cover: X-Content-Type-Options: nosniff,
      // X-DNS-Prefetch-Control, X-Download-Options,
      // X-Permitted-Cross-Domain-Policies, Cross-Origin-Opener-Policy,
      // Origin-Agent-Cluster, and removal of the X-Powered-By header.
    }),
  );

  // JSON parsing middleware
  app.use(express.json());

  // Health check endpoint
  app.get("/healthz", (_req: Request, res: Response) => {
    res.json({ status: "healthy", timestamp: new Date().toISOString() });
  });

  // Readiness check
  app.get("/readyz", (_req: Request, res: Response) => {
    res.json({ status: "ready", timestamp: new Date().toISOString() });
  });

  // BFF session routes. All registered before the /api proxy so they are not
  // forwarded: they are this app's own endpoints, not portal API routes.

  // Login. The shared-library login page speaks a different response dialect
  // than the portal API; `adaptLogin` is the translation seam (see
  // authAdapter.ts). The adapter still yields the refresh token, but it is
  // moved into the HttpOnly cookie here and stripped from the body — the
  // browser only ever receives the short-lived access token (`token`).
  //
  // Login is NOT CSRF-checked: it is authenticated by credentials in the
  // body, not by the session cookie (there is none yet), and it SETS rather
  // than consumes the auth cookie, so a forged cross-site login grants the
  // attacker nothing. SameSite=Strict on the cookies it issues is the
  // backstop. The csrf cookie it sets is what makes the double-submit header
  // available to the subsequent refresh/logout calls.
  app.post("/api/ui/login", async (req: Request, res: Response) => {
    const result = await adaptLogin(
      req.body ?? {},
      `${config.flaskApiUrl}/api/v1/auth/login`,
      fetch,
    );
    const body: Record<string, unknown> = { ...result.body };
    const refresh = body.refreshToken;
    if (
      result.status === 200 &&
      typeof refresh === "string" &&
      refresh.length > 0
    ) {
      setSessionCookies(res, refresh, secure);
    }
    // Never let the refresh token reach the browser in the response body — it
    // exists only in the HttpOnly cookie set above.
    delete body.refreshToken;
    res.status(result.status).json(body);
  });

  // Refresh. Cookie-authenticated: reads the HttpOnly refresh token, calls the
  // backend server-side, rotates the cookie, and returns a fresh access token
  // in the body. The browser never sees the refresh token. CSRF-checked
  // because it is driven by the session cookie.
  app.post("/api/ui/refresh", async (req: Request, res: Response) => {
    if (!csrfValid(req)) {
      return res
        .status(403)
        .json({ error: "CSRF validation failed", errorCode: "CSRF_FAILED" });
    }
    const refresh = parseCookies(req.headers.cookie)[REFRESH_COOKIE];
    if (!refresh) {
      return res
        .status(401)
        .json({ error: "No active session", errorCode: "NO_SESSION" });
    }

    let upstream: Awaited<ReturnType<typeof fetch>>;
    try {
      upstream = await fetch(`${config.flaskApiUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
      console.log("[AuthBff] Refresh upstream unreachable");
      return res.status(502).json({
        error: "Unable to reach the authentication service",
        errorCode: "UPSTREAM_UNAVAILABLE",
      });
    }

    if (!upstream.ok) {
      // The refresh token is dead; clear the cookies so the client stops
      // retrying and falls back to login.
      clearSessionCookies(res, secure);
      console.log(`[AuthBff] Refresh rejected { status: ${upstream.status} }`);
      return res
        .status(401)
        .json({ error: "Session expired", errorCode: "REFRESH_REJECTED" });
    }

    let data: unknown;
    try {
      data = await upstream.json();
    } catch {
      data = {};
    }
    const payload =
      data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const access =
      typeof payload.access_token === "string" ? payload.access_token : null;
    const rotated =
      typeof payload.refresh_token === "string" ? payload.refresh_token : null;

    // Rotate the refresh cookie when the backend issued a new refresh token;
    // keep the existing one otherwise. The CSRF token is always rotated.
    setSessionCookies(res, rotated ?? refresh, secure);
    console.log("[AuthBff] Refresh succeeded");
    return res.json({ access_token: access });
  });

  // Logout. Clears the session cookies. CSRF-checked for the same reason as
  // refresh.
  app.post("/api/ui/logout", (req: Request, res: Response) => {
    if (!csrfValid(req)) {
      return res
        .status(403)
        .json({ error: "CSRF validation failed", errorCode: "CSRF_FAILED" });
    }
    clearSessionCookies(res, secure);
    console.log("[AuthBff] Logout { cleared: true }");
    return res.json({ success: true });
  });

  // Proxy configuration for Flask API (auth, users, hello)
  const flaskProxyOptions: Options = {
    target: config.flaskApiUrl,
    changeOrigin: true,
    pathRewrite: undefined, // Keep original path
    on: {
      // `express.json()` above has already drained the request stream, so
      // the proxy would forward a POST/PUT with no body and the upstream
      // would hang until timeout. fixRequestBody re-serialises the parsed
      // body onto the proxied request.
      proxyReq: (proxyReq, req) => {
        fixRequestBody(proxyReq, req);
        console.log(
          `[Flask Proxy] ${req.method} ${req.url} -> ${config.flaskApiUrl}`,
        );
      },
      error: (err, _req, res) => {
        console.error("[Flask Proxy Error]", err);
        if (res && "writeHead" in res) {
          (res as Response)
            .status(502)
            .json({ error: "Flask API unavailable" });
        }
      },
    },
  };

  // Proxy configuration for Go API (high-performance endpoints)
  const goProxyOptions: Options = {
    target: config.goApiUrl,
    changeOrigin: true,
    pathRewrite: {
      "^/api/go": "/api/v1", // Rewrite /api/go/* to /api/v1/*
    },
    on: {
      proxyReq: (proxyReq, req) => {
        fixRequestBody(proxyReq, req);
        console.log(
          `[Go Proxy] ${req.method} ${req.url} -> ${config.goApiUrl}`,
        );
      },
      error: (err, _req, res) => {
        console.error("[Go Proxy Error]", err);
        if (res && "writeHead" in res) {
          (res as Response).status(502).json({ error: "Go API unavailable" });
        }
      },
    },
  };

  // API proxies
  // Go backend proxy (for high-performance endpoints)
  app.use("/api/go", createProxyMiddleware(goProxyOptions));

  // Flask backend proxy (for auth, users, standard APIs)
  app.use("/api", createProxyMiddleware(flaskProxyOptions));

  // Serve static files in production
  if (config.nodeEnv === "production") {
    app.use(express.static(config.clientDir));

    // SPA fallback - serve index.html for all non-API routes.
    // Express 5 (path-to-regexp v8) rejects a bare "*" path with "Missing
    // parameter name"; the wildcard must be named. Scoped to GET so an
    // unmatched POST/PUT still 404s instead of receiving the HTML shell.
    // `root` + relative filename rather than one absolute path:
    // express/send applies its `dotfiles: "ignore"` rule to every segment
    // it is given, so an absolute path 404s whenever ANY ancestor directory
    // starts with a dot (a git worktree under .worktrees/, a CI workspace,
    // /opt/.releases/...). Scoping to `root` limits that check to the part
    // below clientDir.
    const clientDir = config.clientDir;
    app.get("/*splat", (_req: Request, res: Response) => {
      res.sendFile("index.html", { root: clientDir });
    });
  }

  // Error handling middleware
  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    console.error("Server error:", err);
    res.status(500).json({ error: "Internal server error" });
  });

  return app;
}

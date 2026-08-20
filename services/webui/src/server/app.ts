import express, { Request, Response, NextFunction } from "express";
import path from "path";
import helmet from "helmet";
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

/**
 * Builds the Express app: security headers, the BFF login adapter, the
 * Flask/Go API proxies, and (in production) the static SPA bundle. Building
 * this independently of `app.listen()` is what lets the security-headers
 * test suite exercise the real middleware chain via supertest.
 */
export function createApp(config: AppConfig): express.Express {
  const app = express();

  // Security headers — applied first, before any route or proxy, so every
  // response this origin produces (the SPA shell, its static assets, and the
  // /api proxy responses) carries them. This is the one origin that serves
  // the SPA *and* proxies /api, and the client stores both the access and
  // refresh token in localStorage (see src/client/lib/api.ts) — there is no
  // HttpOnly cookie layer between an XSS and durable account takeover, so
  // CSP is the primary control standing between an injection and a stolen
  // session, not a defense-in-depth nicety.
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
          // BlockPagePreview.tsx renders operator-authored HTML in a
          // sandbox="" srcDoc iframe, never via dangerouslySetInnerHTML. A
          // srcDoc frame has no URL of its own and is checked against the
          // parent's origin, so 'self' is what lets that preview render at
          // all; it does not broaden what the frame can do, since
          // sandbox="" already strips scripts/same-origin/forms/popups from
          // its content.
          frameSrc: ["'self'"],
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

  // BFF login adapter. Registered before the /api proxy so it is not
  // forwarded: the shared-library login page speaks a different response
  // dialect than the portal API, and this endpoint is the translation seam.
  // See authAdapter.ts.
  app.post("/api/ui/login", async (req: Request, res: Response) => {
    const result = await adaptLogin(
      req.body ?? {},
      `${config.flaskApiUrl}/api/v1/auth/login`,
      fetch,
    );
    res.status(result.status).json(result.body);
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

/** Default `clientDir` for a given server module's own directory — the
 * built client bundle sits one level up from `dist/server` at runtime. */
export function defaultClientDir(serverDirname: string): string {
  return path.join(serverDirname, "../client");
}

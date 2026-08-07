import express, { Request, Response, NextFunction } from "express";
import path from "path";
import { fileURLToPath } from "url";
import {
  createProxyMiddleware,
  fixRequestBody,
  Options,
} from "http-proxy-middleware";
import { adaptLogin } from "./authAdapter.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// Configuration from environment
const config = {
  port: parseInt(process.env.PORT || "3000", 10),
  flaskApiUrl: process.env.FLASK_API_URL || "http://localhost:5000",
  goApiUrl: process.env.GO_API_URL || "http://localhost:8080",
  nodeEnv: process.env.NODE_ENV || "development",
};

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

// BFF login adapter. Registered before the /api proxy so it is not forwarded:
// the shared-library login page speaks a different response dialect than the
// portal API, and this endpoint is the translation seam. See authAdapter.ts.
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
    // `express.json()` above has already drained the request stream, so the
    // proxy would forward a POST/PUT with no body and the upstream would hang
    // until timeout. fixRequestBody re-serialises the parsed body onto the
    // proxied request.
    proxyReq: (proxyReq, req) => {
      fixRequestBody(proxyReq, req);
      console.log(
        `[Flask Proxy] ${req.method} ${req.url} -> ${config.flaskApiUrl}`,
      );
    },
    error: (err, _req, res) => {
      console.error("[Flask Proxy Error]", err);
      if (res && "writeHead" in res) {
        (res as Response).status(502).json({ error: "Flask API unavailable" });
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
      console.log(`[Go Proxy] ${req.method} ${req.url} -> ${config.goApiUrl}`);
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
  const clientDir = path.join(__dirname, "../client");
  app.use(express.static(clientDir));

  // SPA fallback - serve index.html for all non-API routes.
  // Express 5 (path-to-regexp v8) rejects a bare "*" path with
  // "Missing parameter name"; the wildcard must be named. Scoped to GET so an
  // unmatched POST/PUT still 404s instead of receiving the HTML shell.
  // `root` + relative filename rather than one absolute path: express/send
  // applies its `dotfiles: "ignore"` rule to every segment it is given, so an
  // absolute path 404s whenever ANY ancestor directory starts with a dot
  // (a git worktree under .worktrees/, a CI workspace, /opt/.releases/...).
  // Scoping to `root` limits that check to the part below clientDir.
  app.get("/*splat", (_req: Request, res: Response) => {
    res.sendFile("index.html", { root: clientDir });
  });
}

// Error handling middleware
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error("Server error:", err);
  res.status(500).json({ error: "Internal server error" });
});

// Start server
app.listen(config.port, () => {
  console.log(`WebUI server running on port ${config.port}`);
  console.log(`Environment: ${config.nodeEnv}`);
  console.log(`Flask API: ${config.flaskApiUrl}`);
  console.log(`Go API: ${config.goApiUrl}`);
});

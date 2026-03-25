import express, { Request, Response, NextFunction } from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { createProxyMiddleware, Options } from 'http-proxy-middleware';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// Configuration from environment
const config = {
  port: parseInt(process.env.PORT || '3000', 10),
  flaskApiUrl: process.env.FLASK_API_URL || 'http://localhost:5000',
  goApiUrl: process.env.GO_API_URL || 'http://localhost:8080',
  nodeEnv: process.env.NODE_ENV || 'development',
};

// JSON parsing middleware
app.use(express.json());

// Health check endpoint
app.get('/healthz', (_req: Request, res: Response) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Readiness check
app.get('/readyz', (_req: Request, res: Response) => {
  res.json({ status: 'ready', timestamp: new Date().toISOString() });
});

// Proxy configuration for Flask API (auth, users, hello)
const flaskProxyOptions: Options = {
  target: config.flaskApiUrl,
  changeOrigin: true,
  pathRewrite: undefined, // Keep original path
  on: {
    proxyReq: (proxyReq, req) => {
      console.log(`[Flask Proxy] ${req.method} ${req.url} -> ${config.flaskApiUrl}`);
    },
    error: (err, _req, res) => {
      console.error('[Flask Proxy Error]', err);
      if (res && 'writeHead' in res) {
        (res as Response).status(502).json({ error: 'Flask API unavailable' });
      }
    },
  },
};

// Proxy configuration for Go API (high-performance endpoints)
const goProxyOptions: Options = {
  target: config.goApiUrl,
  changeOrigin: true,
  pathRewrite: {
    '^/api/go': '/api/v1', // Rewrite /api/go/* to /api/v1/*
  },
  on: {
    proxyReq: (proxyReq, req) => {
      console.log(`[Go Proxy] ${req.method} ${req.url} -> ${config.goApiUrl}`);
    },
    error: (err, _req, res) => {
      console.error('[Go Proxy Error]', err);
      if (res && 'writeHead' in res) {
        (res as Response).status(502).json({ error: 'Go API unavailable' });
      }
    },
  },
};

// API proxies
// Go backend proxy (for high-performance endpoints)
app.use('/api/go', createProxyMiddleware(goProxyOptions));

// Flask backend proxy (for auth, users, standard APIs)
app.use('/api', createProxyMiddleware(flaskProxyOptions));

// Serve static files in production
if (config.nodeEnv === 'production') {
  const clientDir = path.join(__dirname, '../client');
  app.use(express.static(clientDir));

  // SPA fallback - serve index.html for all non-API routes
  app.get('*', (_req: Request, res: Response) => {
    res.sendFile(path.join(clientDir, 'index.html'));
  });
}

// Error handling middleware
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error('Server error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(config.port, () => {
  console.log(`WebUI server running on port ${config.port}`);
  console.log(`Environment: ${config.nodeEnv}`);
  console.log(`Flask API: ${config.flaskApiUrl}`);
  console.log(`Go API: ${config.goApiUrl}`);
});

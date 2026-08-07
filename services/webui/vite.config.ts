import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import fs from "fs";

/**
 * Remove mockServiceWorker.js from production builds — it's only needed in
 * development/test with VITE_MOCKS=true. This prevents the MSW service worker
 * from being included in the production distribution.
 */
function excludeMockServiceWorker() {
  return {
    name: "exclude-mock-service-worker",
    apply: "build",
    resolveId(id: string) {
      if (id.includes("mockServiceWorker.js")) {
        return { id: "", external: true };
      }
    },
    writeBundle() {
      const mockWorkerPath = path.resolve(
        __dirname,
        "dist/client/mockServiceWorker.js",
      );
      if (fs.existsSync(mockWorkerPath)) {
        fs.unlinkSync(mockWorkerPath);
      }
    },
  };
}

export default defineConfig({
  // @tailwindcss/vite is the v4-canonical pipeline for Vite apps; it replaces
  // the PostCSS plugin entirely (no postcss.config.js in this project).
  plugins: [react(), tailwindcss(), excludeMockServiceWorker()],
  root: ".",
  publicDir: "public",
  build: {
    outDir: "dist/client",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src/client"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:3000",
        changeOrigin: true,
      },
    },
  },
});

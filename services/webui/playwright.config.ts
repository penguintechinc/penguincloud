import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for the PenguinCloud portal smoke suite.
 *
 * The dev server runs with VITE_MOCKS=true so the whole flow is served by the
 * MSW handlers in src/client/mocks — no backend required. Artifacts go to
 * /tmp/playwright-penguincloud and are removed by `npm run test:e2e`.
 */
export default defineConfig({
  testDir: "./src/client/tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  // `list` only: an HTML report folder nested under outputDir clashes with the
  // per-test artifact folders, and both are deleted after the run anyway.
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  outputDir: "/tmp/playwright-penguincloud",
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev:client -- --host 127.0.0.1",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    env: { VITE_MOCKS: "true" },
    timeout: 120_000,
  },
});

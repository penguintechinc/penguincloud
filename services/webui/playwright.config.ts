import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for PenguinCloud portal E2E tests
 * Artifacts stored in /tmp/playwright-penguincloud (cleaned after each run)
 */
export default defineConfig({
  testDir: "./src/client/tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html"], ["list"]],
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
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: {
    command: "npm run dev:client",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
  },
});

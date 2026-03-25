/**
 * Playwright Configuration for Smoke Tests
 *
 * Smoke tests validate that:
 * - All pages load without JavaScript errors
 * - Shared components (LoginPageBuilder, FormModalBuilder, SidebarMenu) work correctly
 * - Authentication flows work end-to-end
 * - Tab navigation works on multi-tab pages
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Run local dev server before tests if needed
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        cwd: '../../services/webui',
      },
});

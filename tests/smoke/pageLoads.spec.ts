/**
 * Page Load Smoke Tests
 *
 * Tests that all application pages load without JavaScript errors.
 * Handles both public pages and authentication-protected pages.
 *
 * Configure PAGES array for your application's routes.
 */
import { test, expect } from '@playwright/test';
import { login, collectErrors } from './helpers';

/**
 * Configure your application's pages here
 * Add all pages that should be tested for successful load
 */
const PAGES = [
  // Public pages (no auth required)
  { path: '/login', name: 'Login Page', requiresAuth: false },

  // Protected pages (auth required)
  { path: '/dashboard', name: 'Dashboard', requiresAuth: true },
  // { path: '/users', name: 'Users List', requiresAuth: true },
  // { path: '/settings', name: 'Settings', requiresAuth: true },
  // { path: '/reports', name: 'Reports', requiresAuth: true },

  // Add your application's pages here
];

test.describe('Page Load Smoke Tests', () => {
  test.describe('Public Pages', () => {
    const publicPages = PAGES.filter((p) => !p.requiresAuth);

    for (const page of publicPages) {
      test(`${page.name} (${page.path}) loads without errors`, async ({ page: browserPage }) => {
        const errors = collectErrors(browserPage);

        await browserPage.goto(page.path);
        await browserPage.waitForLoadState('networkidle');

        // Page should have rendered content
        await expect(browserPage.locator('body')).not.toBeEmpty();

        // No JavaScript errors
        expect(errors).toEqual([]);
      });
    }
  });

  test.describe('Protected Pages', () => {
    const protectedPages = PAGES.filter((p) => p.requiresAuth);

    test.beforeEach(async ({ page }) => {
      await login(page);
    });

    for (const pageConfig of protectedPages) {
      test(`${pageConfig.name} (${pageConfig.path}) loads without errors`, async ({ page }) => {
        const errors = collectErrors(page);

        await page.goto(pageConfig.path);
        await page.waitForLoadState('networkidle');

        // Page should have rendered content
        await expect(page.locator('body')).not.toBeEmpty();

        // Should not be redirected to login (auth worked)
        expect(page.url()).not.toContain('/login');

        // No JavaScript errors
        expect(errors).toEqual([]);
      });
    }
  });
});

test.describe('Critical Path Verification', () => {
  test('login flow completes successfully', async ({ page }) => {
    await page.goto('/login');

    // Fill credentials
    await page.fill('input[name="email"]', 'admin@localhost.local');
    await page.fill('input[name="password"]', 'admin123');

    // Submit form
    await page.click('button[type="submit"]');

    // Should redirect away from login
    await page.waitForURL(/\/(dashboard|home|app)/, { timeout: 10000 });
    expect(page.url()).not.toContain('/login');
  });

  test('unauthenticated access redirects to login', async ({ page }) => {
    // Try to access protected page without auth
    await page.goto('/dashboard');

    // Should redirect to login
    await page.waitForURL('**/login**', { timeout: 5000 });
    expect(page.url()).toContain('/login');
  });
});

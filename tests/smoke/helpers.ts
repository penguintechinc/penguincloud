/**
 * Shared Test Helpers for Smoke Tests
 *
 * These helpers support testing pages protected by authentication
 * and validating shared @penguin/react_libs components.
 */
import { Page, expect } from '@playwright/test';

/**
 * Test credentials for smoke tests
 * Uses the default admin user created by Flask-Security-Too
 */
export const TEST_CREDENTIALS = {
  email: process.env.TEST_EMAIL || 'admin@localhost.local',
  password: process.env.TEST_PASSWORD || 'admin123',
};

/**
 * Login helper for authenticated page tests
 */
export async function login(page: Page): Promise<void> {
  await page.goto('/login');

  // Handle GDPR consent if present
  const consentBanner = page.locator('[data-testid="cookie-consent"]');
  if (await consentBanner.isVisible({ timeout: 1000 }).catch(() => false)) {
    await page.click('[data-testid="accept-cookies"]');
  }

  // Fill login form
  await page.fill('input[name="email"]', TEST_CREDENTIALS.email);
  await page.fill('input[name="password"]', TEST_CREDENTIALS.password);
  await page.click('button[type="submit"]');

  // Wait for redirect to dashboard or main app page
  await page.waitForURL(/\/(dashboard|home|app)/, { timeout: 10000 });
}

/**
 * Collect JavaScript errors during page navigation
 */
export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => {
    errors.push(error.message);
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}

/**
 * Verify a page loads without JavaScript errors
 */
export async function verifyPageLoads(
  page: Page,
  path: string,
  options: { requiresAuth?: boolean; waitForSelector?: string } = {}
): Promise<void> {
  const errors = collectErrors(page);

  if (options.requiresAuth) {
    await login(page);
  }

  await page.goto(path);
  await page.waitForLoadState('networkidle');

  if (options.waitForSelector) {
    await page.waitForSelector(options.waitForSelector);
  }

  expect(errors).toEqual([]);
}

/**
 * Verify a tab loads without errors
 */
export async function verifyTabLoads(
  page: Page,
  tabSelector: string,
  contentSelector?: string
): Promise<void> {
  const errors = collectErrors(page);

  await page.click(tabSelector);
  await page.waitForLoadState('networkidle');

  if (contentSelector) {
    await expect(page.locator(contentSelector)).toBeVisible();
  }

  expect(errors).toEqual([]);
}

/**
 * Verify a form modal opens and closes correctly
 */
export async function verifyFormModal(
  page: Page,
  triggerSelector: string,
  expectedTitle: string
): Promise<void> {
  const errors = collectErrors(page);

  // Open modal
  await page.click(triggerSelector);
  await expect(page.locator('[role="dialog"]')).toBeVisible();

  // Verify title
  const modalTitle = page.locator('[role="dialog"] h2, [role="dialog"] [data-testid="modal-title"]');
  await expect(modalTitle).toContainText(expectedTitle);

  // Close modal
  const closeButton = page.locator(
    '[data-testid="modal-close"], [role="dialog"] button[aria-label="Close"]'
  );
  await closeButton.click();
  await expect(page.locator('[role="dialog"]')).not.toBeVisible();

  expect(errors).toEqual([]);
}

/**
 * Verify form validation shows errors for required fields
 */
export async function verifyFormValidation(
  page: Page,
  triggerSelector: string
): Promise<void> {
  // Open modal
  await page.click(triggerSelector);
  await expect(page.locator('[role="dialog"]')).toBeVisible();

  // Submit empty form
  await page.click('[role="dialog"] button[type="submit"]');

  // Modal should still be visible (form didn't submit)
  await expect(page.locator('[role="dialog"]')).toBeVisible();

  // Validation errors should be shown
  const errorText = page.locator('.text-red-400, .text-red-500, [data-testid="field-error"]');
  await expect(errorText.first()).toBeVisible();

  // Close modal
  await page.click('[data-testid="modal-close"], [role="dialog"] button[aria-label="Close"]');
}

/**
 * Verify sidebar navigation works
 */
export async function verifySidebarNavigation(
  page: Page,
  menuItems: { name: string; expectedPath: string }[]
): Promise<void> {
  for (const item of menuItems) {
    const menuLink = page.locator(`[data-testid="sidebar-menu"] a:has-text("${item.name}")`);
    await menuLink.click();
    await page.waitForURL(`**${item.expectedPath}**`);
    expect(page.url()).toContain(item.expectedPath);
  }
}

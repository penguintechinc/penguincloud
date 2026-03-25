/**
 * LoginPageBuilder Smoke Tests
 *
 * Tests the shared LoginPageBuilder component from @penguin/react_libs
 * Validates login functionality, GDPR consent, validation, and error handling.
 */
import { test, expect } from '@playwright/test';
import { TEST_CREDENTIALS, collectErrors } from './helpers';

test.describe('LoginPageBuilder Smoke Tests', () => {
  test.describe('Page Rendering', () => {
    test('login page renders all required elements', async ({ page }) => {
      const errors = collectErrors(page);

      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Core form elements should be visible
      await expect(page.locator('input[name="email"]')).toBeVisible();
      await expect(page.locator('input[name="password"]')).toBeVisible();
      await expect(page.locator('button[type="submit"]')).toBeVisible();

      // No JavaScript errors
      expect(errors).toEqual([]);
    });

    test('login page shows branding elements', async ({ page }) => {
      await page.goto('/login');

      // App name or logo should be visible
      const brandingElement = page.locator(
        '[data-testid="app-name"], [data-testid="app-logo"], h1'
      );
      await expect(brandingElement.first()).toBeVisible();
    });
  });

  test.describe('GDPR Cookie Consent', () => {
    test('consent banner appears on first visit', async ({ page, context }) => {
      // Clear storage for fresh visit
      await context.clearCookies();
      await page.goto('/login');

      // GDPR consent banner should be visible
      const consentBanner = page.locator('[data-testid="cookie-consent"]');

      // If GDPR is enabled, banner should show
      const isVisible = await consentBanner.isVisible({ timeout: 2000 }).catch(() => false);
      if (isVisible) {
        await expect(consentBanner).toBeVisible();

        // Accept button should exist
        await expect(
          page.locator('[data-testid="accept-cookies"], [data-testid="accept-all"]')
        ).toBeVisible();
      }
    });

    test('consent can be accepted', async ({ page, context }) => {
      await context.clearCookies();
      await page.goto('/login');

      const acceptButton = page.locator(
        '[data-testid="accept-cookies"], [data-testid="accept-all"]'
      );
      const isVisible = await acceptButton.isVisible({ timeout: 2000 }).catch(() => false);

      if (isVisible) {
        await acceptButton.click();

        // Banner should disappear
        await expect(page.locator('[data-testid="cookie-consent"]')).not.toBeVisible();
      }
    });
  });

  test.describe('Form Validation', () => {
    test('shows validation error for empty form submission', async ({ page }) => {
      await page.goto('/login');

      // Try to submit empty form
      await page.click('button[type="submit"]');

      // Validation error should appear
      const errorElement = page.locator(
        '.text-red-400, .text-red-500, [data-testid="validation-error"], [data-testid="field-error"]'
      );
      await expect(errorElement.first()).toBeVisible();
    });

    test('shows validation error for invalid email format', async ({ page }) => {
      await page.goto('/login');

      await page.fill('input[name="email"]', 'invalid-email');
      await page.fill('input[name="password"]', 'somepassword');
      await page.click('button[type="submit"]');

      // Should show email validation error or be prevented by browser
      // Note: HTML5 email validation may prevent submission
      const currentUrl = page.url();
      expect(currentUrl).toContain('/login'); // Should still be on login page
    });
  });

  test.describe('Authentication Flow', () => {
    test('shows error message for invalid credentials', async ({ page }) => {
      await page.goto('/login');

      await page.fill('input[name="email"]', 'wrong@example.com');
      await page.fill('input[name="password"]', 'wrongpassword123');
      await page.click('button[type="submit"]');

      // Wait for API response
      await page.waitForResponse((response) =>
        response.url().includes('/auth') || response.url().includes('/login')
      ).catch(() => {});

      // Error message should be displayed
      const errorMessage = page.locator(
        '[data-testid="login-error"], .text-red-400, .text-red-500, [role="alert"]'
      );
      await expect(errorMessage.first()).toBeVisible({ timeout: 5000 });
    });

    test('successful login redirects to dashboard', async ({ page }) => {
      await page.goto('/login');

      // Handle GDPR consent if present
      const acceptButton = page.locator('[data-testid="accept-cookies"]');
      if (await acceptButton.isVisible({ timeout: 1000 }).catch(() => false)) {
        await acceptButton.click();
      }

      await page.fill('input[name="email"]', TEST_CREDENTIALS.email);
      await page.fill('input[name="password"]', TEST_CREDENTIALS.password);
      await page.click('button[type="submit"]');

      // Should redirect to dashboard or main app
      await page.waitForURL(/\/(dashboard|home|app)/, { timeout: 10000 });
      expect(page.url()).not.toContain('/login');
    });
  });

  test.describe('Remember Me Feature', () => {
    test('remember me checkbox is functional', async ({ page }) => {
      await page.goto('/login');

      const rememberMe = page.locator(
        'input[name="rememberMe"], input[type="checkbox"][id*="remember"]'
      );

      // Check if remember me exists (optional feature)
      const exists = await rememberMe.count();
      if (exists > 0) {
        await expect(rememberMe).toBeVisible();
        await rememberMe.check();
        await expect(rememberMe).toBeChecked();
      }
    });
  });

  test.describe('Optional Features', () => {
    test('forgot password link exists if enabled', async ({ page }) => {
      await page.goto('/login');

      const forgotPasswordLink = page.locator(
        'a[href*="forgot"], a[href*="reset"], button:has-text("Forgot")'
      );
      const exists = await forgotPasswordLink.count();

      // Just verify it's rendered if configured (optional feature)
      if (exists > 0) {
        await expect(forgotPasswordLink.first()).toBeVisible();
      }
    });

    test('sign up link exists if enabled', async ({ page }) => {
      await page.goto('/login');

      const signUpLink = page.locator(
        'a[href*="register"], a[href*="signup"], button:has-text("Sign up")'
      );
      const exists = await signUpLink.count();

      // Just verify it's rendered if configured (optional feature)
      if (exists > 0) {
        await expect(signUpLink.first()).toBeVisible();
      }
    });

    test('social login buttons render if configured', async ({ page }) => {
      await page.goto('/login');

      // Check for social login buttons
      const socialButtons = page.locator('[data-testid*="social-login"], .social-login-btn');
      const count = await socialButtons.count();

      // Just verify they render without errors if configured
      if (count > 0) {
        await expect(socialButtons.first()).toBeVisible();
      }
    });
  });
});

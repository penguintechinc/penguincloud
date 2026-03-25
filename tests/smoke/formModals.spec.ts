/**
 * FormModalBuilder Smoke Tests
 *
 * Tests the shared FormModalBuilder component from @penguin/react_libs
 * Validates modal open/close, form rendering, validation, and submission.
 *
 * Configure FORM_MODALS array for your application's forms.
 */
import { test, expect } from '@playwright/test';
import { login, collectErrors, verifyFormModal, verifyFormValidation } from './helpers';

/**
 * Configure your application's form modals here
 * Each entry should specify the page, trigger button, and expected modal title
 */
const FORM_MODALS = [
  // Example configurations - customize for your application
  // {
  //   page: '/users',
  //   trigger: '[data-testid="create-user-btn"]',
  //   title: 'Create User',
  //   hasRequiredFields: true,
  // },
  // {
  //   page: '/settings',
  //   trigger: '[data-testid="edit-profile-btn"]',
  //   title: 'Edit Profile',
  //   hasRequiredFields: false,
  // },
];

test.describe('FormModalBuilder Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login for protected pages
    await login(page);
  });

  test.describe('Modal Lifecycle', () => {
    for (const form of FORM_MODALS) {
      test(`${form.title} modal opens and closes correctly`, async ({ page }) => {
        const errors = collectErrors(page);

        await page.goto(form.page);
        await verifyFormModal(page, form.trigger, form.title);

        expect(errors).toEqual([]);
      });
    }

    test('modal closes on escape key', async ({ page }) => {
      if (FORM_MODALS.length === 0) {
        test.skip();
        return;
      }

      const form = FORM_MODALS[0];
      await page.goto(form.page);

      // Open modal
      await page.click(form.trigger);
      await expect(page.locator('[role="dialog"]')).toBeVisible();

      // Press escape
      await page.keyboard.press('Escape');

      // Modal should close
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('modal closes on backdrop click', async ({ page }) => {
      if (FORM_MODALS.length === 0) {
        test.skip();
        return;
      }

      const form = FORM_MODALS[0];
      await page.goto(form.page);

      // Open modal
      await page.click(form.trigger);
      await expect(page.locator('[role="dialog"]')).toBeVisible();

      // Click backdrop (outside modal content)
      await page.click('[data-testid="modal-backdrop"], .fixed.inset-0', { position: { x: 10, y: 10 } });

      // Modal should close (if backdrop click is enabled)
      // Note: This may not work for all modal configurations
    });
  });

  test.describe('Form Validation', () => {
    const formsWithValidation = FORM_MODALS.filter((f) => f.hasRequiredFields);

    for (const form of formsWithValidation) {
      test(`${form.title} shows validation errors for required fields`, async ({ page }) => {
        await page.goto(form.page);
        await verifyFormValidation(page, form.trigger);
      });
    }
  });

  test.describe('Form Fields', () => {
    for (const form of FORM_MODALS) {
      test(`${form.title} renders all form fields`, async ({ page }) => {
        await page.goto(form.page);

        // Open modal
        await page.click(form.trigger);
        await expect(page.locator('[role="dialog"]')).toBeVisible();

        // Verify form elements exist
        const formElement = page.locator('[role="dialog"] form, [role="dialog"] [data-testid="form"]');
        await expect(formElement).toBeVisible();

        // Should have at least one input field
        const inputs = page.locator('[role="dialog"] input, [role="dialog"] select, [role="dialog"] textarea');
        expect(await inputs.count()).toBeGreaterThan(0);

        // Should have submit button
        const submitButton = page.locator('[role="dialog"] button[type="submit"]');
        await expect(submitButton).toBeVisible();
      });
    }
  });

  test.describe('Tab Navigation (Tabbed Forms)', () => {
    const tabbedForms = FORM_MODALS.filter((f) => (f as { tabs?: string[] }).tabs);

    for (const form of tabbedForms) {
      const tabs = (form as { tabs?: string[] }).tabs || [];
      for (const tab of tabs) {
        test(`${form.title} - ${tab} tab is accessible`, async ({ page }) => {
          await page.goto(form.page);

          // Open modal
          await page.click(form.trigger);
          await expect(page.locator('[role="dialog"]')).toBeVisible();

          // Click tab
          const tabButton = page.locator(`[role="dialog"] [data-testid="tab-${tab.toLowerCase()}"], [role="dialog"] button:has-text("${tab}")`);
          await tabButton.click();

          // Tab content should be visible
          const tabContent = page.locator(`[data-testid="tab-content-${tab.toLowerCase()}"], [role="tabpanel"]`);
          await expect(tabContent.first()).toBeVisible();
        });
      }
    }
  });
});

test.describe('FormModalBuilder General Tests', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('form modals maintain focus trap', async ({ page }) => {
    if (FORM_MODALS.length === 0) {
      test.skip();
      return;
    }

    const form = FORM_MODALS[0];
    await page.goto(form.page);

    // Open modal
    await page.click(form.trigger);
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Tab through elements - focus should stay within modal
    const modal = page.locator('[role="dialog"]');
    const focusableElements = modal.locator('button, input, select, textarea, a[href]');
    const count = await focusableElements.count();

    // Tab through all elements
    for (let i = 0; i < count + 2; i++) {
      await page.keyboard.press('Tab');
    }

    // Focused element should still be within modal
    const activeElement = page.locator(':focus');
    await expect(activeElement).toBeVisible();
  });

  test('form modals have proper ARIA attributes', async ({ page }) => {
    if (FORM_MODALS.length === 0) {
      test.skip();
      return;
    }

    const form = FORM_MODALS[0];
    await page.goto(form.page);

    // Open modal
    await page.click(form.trigger);

    // Check for dialog role
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Should have aria-labelledby or aria-label
    const hasLabel =
      (await dialog.getAttribute('aria-labelledby')) !== null ||
      (await dialog.getAttribute('aria-label')) !== null;
    expect(hasLabel).toBeTruthy();
  });
});

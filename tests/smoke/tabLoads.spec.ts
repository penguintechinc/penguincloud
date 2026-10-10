/**
 * Tab Load Smoke Tests
 *
 * Tests that all tabs on multi-tab pages load without errors.
 * Validates tab navigation and content rendering.
 *
 * Configure TABBED_PAGES array for your application's tabbed pages.
 */
import { test, expect } from '@playwright/test';
import { login, collectErrors } from './helpers';

/**
 * Configure your application's tabbed pages here
 * Each entry should specify the page path and list of tabs to test
 */
const TABBED_PAGES = [
  // Example configurations - customize for your application
  // {
  //   path: '/settings',
  //   name: 'Settings',
  //   tabs: [
  //     { id: 'general', label: 'General' },
  //     { id: 'security', label: 'Security' },
  //     { id: 'notifications', label: 'Notifications' },
  //   ],
  // },
  // {
  //   path: '/users/1',
  //   name: 'User Details',
  //   tabs: [
  //     { id: 'profile', label: 'Profile' },
  //     { id: 'permissions', label: 'Permissions' },
  //     { id: 'activity', label: 'Activity' },
  //   ],
  // },
];

test.describe('Tab Load Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  for (const tabbedPage of TABBED_PAGES) {
    test.describe(`${tabbedPage.name} (${tabbedPage.path})`, () => {
      test.beforeEach(async ({ page }) => {
        await page.goto(tabbedPage.path);
        await page.waitForLoadState('networkidle');
      });

      test('page loads with tabs visible', async ({ page }) => {
        const errors = collectErrors(page);

        // At least one tab should be visible
        const tabList = page.locator('[role="tablist"], .tabs, [data-testid="tab-list"]');
        await expect(tabList).toBeVisible();

        expect(errors).toEqual([]);
      });

      test('first tab is active by default', async ({ page }) => {
        const firstTab = tabbedPage.tabs[0];
        const tabButton = page.locator(
          `[data-testid="tab-${firstTab.id}"], button:has-text("${firstTab.label}")`
        ).first();

        // Should have active state
        const isActive =
          (await tabButton.getAttribute('aria-selected')) === 'true' ||
          (await tabButton.getAttribute('data-state')) === 'active' ||
          (await tabButton.getAttribute('class'))?.includes('active');

        expect(isActive).toBeTruthy();
      });

      for (const tab of tabbedPage.tabs) {
        test(`${tab.label} tab loads without errors`, async ({ page }) => {
          const errors = collectErrors(page);

          // Click tab
          const tabButton = page.locator(
            `[data-testid="tab-${tab.id}"], button:has-text("${tab.label}")`
          ).first();
          await tabButton.click();

          // Wait for content to load
          await page.waitForLoadState('networkidle');

          // Tab panel should be visible
          const tabPanel = page.locator(
            `[data-testid="tab-content-${tab.id}"], [role="tabpanel"]:visible, [data-state="active"]`
          );
          await expect(tabPanel.first()).toBeVisible();

          expect(errors).toEqual([]);
        });
      }

      test('tab navigation via keyboard', async ({ page }) => {
        if (tabbedPage.tabs.length < 2) {
          test.skip();
          return;
        }

        // Focus first tab
        const firstTabButton = page.locator(
          `[data-testid="tab-${tabbedPage.tabs[0].id}"], button:has-text("${tabbedPage.tabs[0].label}")`
        ).first();
        await firstTabButton.focus();

        // Press arrow right to move to next tab
        await page.keyboard.press('ArrowRight');

        // Second tab should now be focused/active
        const secondTabButton = page.locator(
          `[data-testid="tab-${tabbedPage.tabs[1].id}"], button:has-text("${tabbedPage.tabs[1].label}")`
        ).first();

        const isFocused = await secondTabButton.evaluate(
          (el) => document.activeElement === el
        );
        expect(isFocused).toBeTruthy();
      });
    });
  }
});

test.describe('Tab Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  for (const tabbedPage of TABBED_PAGES) {
    test(`${tabbedPage.name} tabs have proper ARIA attributes`, async ({ page }) => {
      await page.goto(tabbedPage.path);

      // Tab list should have role="tablist"
      const tabList = page.locator('[role="tablist"]');
      const hasTabList = (await tabList.count()) > 0;

      if (hasTabList) {
        // Each tab should have role="tab"
        const tabs = page.locator('[role="tab"]');
        expect(await tabs.count()).toBeGreaterThan(0);

        // Active tab should have aria-selected="true"
        const activeTab = page.locator('[role="tab"][aria-selected="true"]');
        expect(await activeTab.count()).toBe(1);

        // Tab panels should have role="tabpanel"
        const panels = page.locator('[role="tabpanel"]');
        expect(await panels.count()).toBeGreaterThan(0);
      }
    });
  }
});

test.describe('Tab State Persistence', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  for (const tabbedPage of TABBED_PAGES) {
    test(`${tabbedPage.name} maintains tab state on refresh`, async ({ page }) => {
      if (tabbedPage.tabs.length < 2) {
        test.skip();
        return;
      }

      await page.goto(tabbedPage.path);

      // Click second tab
      const secondTab = tabbedPage.tabs[1];
      const tabButton = page.locator(
        `[data-testid="tab-${secondTab.id}"], button:has-text("${secondTab.label}")`
      ).first();
      await tabButton.click();

      // Get current URL (may include tab state in URL)
      const urlAfterClick = page.url();

      // Refresh page
      await page.reload();
      await page.waitForLoadState('networkidle');

      // Check if tab state persisted via URL
      if (urlAfterClick.includes(secondTab.id) || urlAfterClick.includes('tab=')) {
        // URL-based persistence - tab should still be active
        const isActive =
          (await tabButton.getAttribute('aria-selected')) === 'true' ||
          (await tabButton.getAttribute('data-state')) === 'active';
        expect(isActive).toBeTruthy();
      }
      // Note: If not URL-based, state persistence is not guaranteed
    });
  }
});

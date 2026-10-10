/**
 * Portal shell smoke test, run against the MSW-mocked build.
 *
 * Covers the acting-as round trip end to end: login → dashboard → switch into
 * a customer tenant → banner → exit → logout, plus the responsive checks at
 * 320/768/1024.
 */

import { test, expect, type Page } from "@playwright/test";

const EMAIL = "admin@penguincloud.test";
const PASSWORD = "correct-horse";

/** Provider org and one of its customers, per src/client/mocks/fixtures.ts. */
const PROVIDER_LABEL = "Acme Corp (Provider)";
const CUSTOMER_ID = 11;
const CUSTOMER_LABEL = "Acme Production";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test.describe("portal shell", () => {
  test("login → dashboard → switch → banner → exit → logout", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await login(page);
    await expect(page.getByTestId("tenant-scope-switcher")).toBeVisible();
    await expect(page.getByTestId("acting-as-banner")).toBeHidden();

    // Switch into a customer tenant.
    await page.getByTestId("tenant-switcher-button").click();
    await expect(page.getByTestId("tenant-switcher-search")).toBeVisible();
    await page.getByTestId(`tenant-option-${CUSTOMER_ID}`).click();

    // Acting-as banner appears and names the customer.
    const banner = page.getByTestId("acting-as-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(CUSTOMER_LABEL);
    await expect(banner).toHaveAttribute("role", "status");
    await expect(page).toHaveURL(new RegExp(`tenant=${CUSTOMER_ID}`));

    // Exit returns to the home tenant and removes the banner.
    await page.getByTestId("exit-acting-as-button").click();
    await expect(banner).toBeHidden();
    await expect(page.getByTestId("tenant-switcher-button")).toContainText(
      PROVIDER_LABEL,
    );

    // Logout lands back on the login page.
    await page.getByTestId("logout-button").click();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();

    expect(consoleErrors).toEqual([]);
  });

  test("provider scope shows the customers rollup matrix", async ({ page }) => {
    await login(page);

    await page.getByRole("button", { name: "Customers" }).click();

    const matrix = page.getByTestId("rollup-matrix");
    await expect(matrix).toBeVisible();
    await expect(matrix.getByText("Acme Production")).toBeVisible();
    await expect(matrix.getByText("Acme Staging")).toBeVisible();
    // Only this provider's customers — never the other provider's.
    await expect(matrix.getByText("TechVision Platform")).toBeHidden();
  });

  test("rejects bad credentials without navigating", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(EMAIL);
    await page.getByLabel(/password/i).fill("wrong");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByText("Invalid email or password")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  const viewports = [
    { name: "mobile", width: 320, height: 640 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "desktop", width: 1024, height: 768 },
  ];

  for (const viewport of viewports) {
    test(`renders the shell at ${viewport.width}px (${viewport.name})`, async ({
      page,
    }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await login(page);

      // Chrome is reachable at every width; below lg the sidebar is behind the
      // hamburger toggle rather than always on screen.
      await expect(page.getByTestId("tenant-scope-switcher")).toBeVisible();

      const toggle = page.getByRole("button", { name: "Toggle menu" });
      if (viewport.width < 1024) {
        await expect(toggle).toBeVisible();
        await toggle.click();
        // The shared SidebarMenu keeps a hidden desktop <nav> mounted below
        // lg, so target the one that is actually on screen.
        await expect(
          page.locator("nav:visible").getByText("Health"),
        ).toBeVisible();
      } else {
        await expect(toggle).toBeHidden();
      }

      // No horizontal overflow at any width.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      expect(overflow).toBe(false);
    });
  }
});

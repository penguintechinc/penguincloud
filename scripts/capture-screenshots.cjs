const path = require('path');
const fs = require('fs');

// This script lives at the repo root (scripts/), but `@playwright/test` is a
// devDependency of services/webui only — there is no root package.json/
// node_modules for plain `require` to walk up into. Node resolves relative
// to the FILE's own directory, not cwd, so this was true (and this script
// was never actually runnable, with puppeteer in the same spot before it)
// regardless of whether it's invoked as `node scripts/capture-screenshots.cjs`
// from the repo root or `npm run screenshots` from services/webui.
const WEBUI_DIR = path.join(__dirname, '..', 'services', 'webui');
const { chromium } = require(
  require.resolve('@playwright/test', { paths: [WEBUI_DIR] }),
);

// Default target is the MSW-mocked Vite dev server (`npm run dev:client:mocks`,
// port 5173) — the same "no backend required" mode services/webui's own
// Playwright smoke suite uses (see playwright.config.ts / mocks/browser.ts).
// There is no seeded Postgres/portal-api instance available to this script
// (`make seed-mock-data` is an unimplemented stub — see Makefile), so the
// dashboard/tenants/users/connections/health data below comes entirely from
// the fixtures baked into src/client/mocks/fixtures.ts, not a live database.
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:5173';
const OUTPUT_DIR = path.join(__dirname, '..', 'docs', 'screenshots');

// Playwright's own debug artifacts (trace), not the deliverable screenshots
// above — see testing.md's Playwright Artifact Management. Removed after
// every run, pass or fail, same as npm run test:e2e's outputDir handling.
const ARTIFACTS_DIR = '/tmp/playwright-penguincloud';

// Matches services/webui's own portal-smoke.spec.ts fixture credentials
// (src/client/mocks/fixtures.ts / handlers.ts `/api/ui/login`) — any
// email/password pair authenticates in mock mode except password==="wrong",
// but using the same credentials as the tested e2e suite keeps this script
// aligned with a path that is already known to work end-to-end.
const TEST_EMAIL = 'admin@penguincloud.test';
const TEST_PASSWORD = 'correct-horse';

// Customer tenant to switch into before capturing pages whose data depends
// on the active tenant scope (Health, Connections). Per fixtures.ts, the
// home tenant (Acme Corp, id 1) is a *provider* org with no products of its
// own — only customer tenants 11 and 13 have MOCK_PRODUCTS_BY_TENANT entries.
// Tenant 11 (Acme Production) has 3 connected products, the richest fixture.
const CUSTOMER_TENANT_ID = 11;

/**
 * Pages captured against the MSW-mocked dev server. Each entry is verified
 * against src/client/mocks/handlers.ts's actual endpoint coverage before
 * being listed here — a page whose data-fetching hook has no matching
 * handler is deliberately left off this list rather than shipped with a
 * misleading empty/error state. See the capture run's own report for the
 * specific gaps (audit logs, teams, tenant/user/connection detail routes,
 * the generic product page, and the Gough/Nest/Tobogganing product-specific
 * screens all need mock or real-backend coverage this script does not have).
 */
const pages = [
  { name: 'login', path: '/login', requiresAuth: false },
  { name: 'dashboard', path: '/' },
  { name: 'tenants', path: '/tenants' },
  { name: 'tenants-new', path: '/tenants/new' },
  { name: 'users', path: '/users' },
  { name: 'profile', path: '/profile' },
  { name: 'settings', path: '/settings' },
  // Requires the tenant switch below — see requiresCustomerTenant.
  { name: 'health', path: '/health', requiresCustomerTenant: true },
  { name: 'connections', path: '/connections', requiresCustomerTenant: true },
  // NOTE: /connections/new (Register Product Connection) is deliberately
  // NOT captured here. Its step 1 lists selectable product types from
  // GET /api/v1/products/types, which has no MSW handler — the wizard
  // renders "Select the product type to connect:" followed by zero options,
  // an empty step masquerading as a working flow. Per the screenshot skill's
  // Step 4 checklist ("empty state standing in for what should be populated
  // content"), this is not shipped; see the capture run's report instead.
];

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function removeOldScreenshots() {
  if (fs.existsSync(OUTPUT_DIR)) {
    const files = fs.readdirSync(OUTPUT_DIR);
    files.forEach(file => {
      if (file.endsWith('.png')) {
        const filePath = path.join(OUTPUT_DIR, file);
        fs.unlinkSync(filePath);
        console.log(`Removed old screenshot: ${file}`);
      }
    });
  }
}

/**
 * Switches the active tenant scope via the real sidebar UI (not a direct
 * store/localStorage write) so the capture run exercises the same flow
 * services/webui's portal-smoke.spec.ts already verifies end to end.
 */
async function switchToCustomerTenant(page) {
  await page.getByTestId('tenant-switcher-button').click();
  await page.getByTestId('tenant-switcher-search').waitFor({ state: 'visible' });
  await page.getByTestId(`tenant-option-${CUSTOMER_TENANT_ID}`).click();
  await page
    .getByTestId('acting-as-banner')
    .waitFor({ state: 'visible', timeout: 10000 });
}

async function captureScreenshots() {
  // Remove old screenshots first
  await removeOldScreenshots();

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();

  let switchedToCustomerTenant = false;

  try {
    // Capture login page first (unauthenticated)
    console.log('Capturing login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 60000 });
    await sleep(1000);
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'login.png') });
    console.log('  Saved login.png');

    // Perform actual login through UI, via the shared LoginPageBuilder's
    // accessible labels rather than positional input selectors — matches
    // services/webui/src/client/tests/e2e/portal-smoke.spec.ts.
    console.log(`Logging in with test credentials (${TEST_EMAIL})...`);
    await page.getByLabel(/email/i).fill(TEST_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();

    try {
      await page.waitForFunction(
        () => !window.location.pathname.includes('/login'),
        undefined,
        { timeout: 30000 },
      );
    } catch (e) {
      console.log('Navigation timeout - checking if login succeeded anyway');
    }
    await sleep(2000);
    console.log('Current URL after login:', page.url());

    // Verify we're logged in
    const isLoggedIn = await page.evaluate(() => {
      return localStorage.getItem('token') !== null ||
             localStorage.getItem('access_token') !== null ||
             !window.location.pathname.includes('/login');
    });

    if (!isLoggedIn) {
      console.error('❌ Login failed! Cannot capture authenticated pages.');
      console.error('   Ensure the MSW-mocked dev server is running: BASE_URL should point');
      console.error('   at `npm run dev:client:mocks` (services/webui), not a bare `npm run dev`.');
      return;
    }
    console.log('✓ Login successful!');

    // Capture all other pages
    let successCount = 0;
    let skipCount = 0;
    let errorCount = 0;

    for (const pageInfo of pages) {
      if (pageInfo.name === 'login') continue;

      try {
        console.log(`Capturing ${pageInfo.name}...`);

        if (pageInfo.requiresCustomerTenant && !switchedToCustomerTenant) {
          console.log(
            `  Switching to customer tenant ${CUSTOMER_TENANT_ID} (Acme Production)...`,
          );
          await switchToCustomerTenant(page);
          switchedToCustomerTenant = true;
        }

        // Navigate to the page
        await page.goto(`${BASE_URL}${pageInfo.path}`, {
          waitUntil: 'networkidle',
          timeout: 60000,
        });

        // Wait for content to load
        await sleep(2500);

        // Check if we got redirected to login (session expired or auth issue)
        const currentUrl = page.url();
        if (currentUrl.includes('/login')) {
          console.log(`  WARNING: Redirected to login for ${pageInfo.name}`);

          // Try to re-login
          console.log('  Attempting re-login...');
          await page.getByLabel(/email/i).fill(TEST_EMAIL);
          await page.getByLabel(/password/i).fill(TEST_PASSWORD);
          await page.getByRole('button', { name: /sign in/i }).click();
          await sleep(2000);

          // Navigate back to the target page
          await page.goto(`${BASE_URL}${pageInfo.path}`, {
            waitUntil: 'networkidle',
            timeout: 60000,
          });
          await sleep(2500);

          // Check again
          const newUrl = page.url();
          if (newUrl.includes('/login')) {
            console.log(`  SKIP: Still redirected to login for ${pageInfo.name}`);
            skipCount++;
            continue;
          }
        }

        // Take screenshot
        await page.screenshot({
          path: path.join(OUTPUT_DIR, `${pageInfo.name}.png`),
          fullPage: false,
        });
        console.log(`  ✓ Saved ${pageInfo.name}.png`);
        successCount++;

        // The Dashboard's default "Overview" tab is thin for a provider
        // tenant (a provider owns no products directly — only its customer
        // tenants do), so it alone doesn't show the product's actual
        // multi-tenant rollup value. Capture the "Customers" tab too, the
        // same rollup-matrix view exercised by portal-smoke.spec.ts.
        if (pageInfo.name === 'dashboard') {
          console.log('Capturing dashboard-rollup (Customers tab)...');
          await page.getByRole('button', { name: 'Customers' }).click();
          await page.getByTestId('rollup-matrix').waitFor({ state: 'visible' });
          await sleep(500);
          await page.screenshot({
            path: path.join(OUTPUT_DIR, 'dashboard-rollup.png'),
            fullPage: false,
          });
          console.log('  ✓ Saved dashboard-rollup.png');
          successCount++;
        }

      } catch (error) {
        console.error(`  ✗ Error capturing ${pageInfo.name}: ${error.message}`);
        errorCount++;
      }
    }

    console.log('\n========================================');
    console.log('Screenshot capture complete!');
    console.log(`  ✓ Success: ${successCount}`);
    console.log(`  ⊘ Skipped: ${skipCount}`);
    console.log(`  ✗ Errors:  ${errorCount}`);
    console.log(`  📁 Output:  ${OUTPUT_DIR}`);
    console.log('========================================\n');
  } finally {
    await context.tracing.stop({ path: path.join(ARTIFACTS_DIR, 'trace.zip') });
    await browser.close();
    // Cleaned up on both the success path and every throw above — see
    // testing.md's Playwright Artifact Management (never leave artifacts in
    // /tmp after completion).
    fs.rmSync(ARTIFACTS_DIR, { recursive: true, force: true });
  }
}

captureScreenshots().catch(console.error);

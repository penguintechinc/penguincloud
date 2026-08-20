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

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const OUTPUT_DIR = path.join(__dirname, '..', 'docs', 'screenshots');

// Playwright's own debug artifacts (trace), not the deliverable screenshots
// above — see testing.md's Playwright Artifact Management. Removed after
// every run, pass or fail, same as npm run test:e2e's outputDir handling.
const ARTIFACTS_DIR = '/tmp/playwright-penguincloud';

// The login page's email input is `type="email" pattern="[^\s@]+@[^\s@]+\.
// [^\s@]+"` (LoginPageBuilder, @penguintechinc/react-libs) — a bare
// "admin@localhost" (no TLD) fails that pattern and the browser silently
// blocks submission before it ever reaches the mock. ".local" is a real TLD
// suffix and is what the field's own placeholder/title suggest as an example.
const TEST_EMAIL = 'admin@localhost.local';
const TEST_PASSWORD = 'admin123';

// Pages to capture - customize with your application routes
const pages = [
  { name: 'login', path: '/login', requiresAuth: false },
  { name: 'dashboard', path: '/' },
  // Add your additional pages here:
  // { name: 'products', path: '/products' },
  // { name: 'orders', path: '/orders' },
  // { name: 'settings', path: '/settings' },
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

  try {
    // Capture login page first (unauthenticated)
    console.log('Capturing login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 60000 });
    await sleep(1000);
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'login.png') });
    console.log('  Saved login.png');

    // Perform actual login through UI
    console.log(`Logging in with test credentials (${TEST_EMAIL})...`);

    // Find and fill login form - email field, password field
    const inputCount = await page.locator('input').count();
    console.log(`Found ${inputCount} input fields`);
    if (inputCount >= 2) {
      await page.locator('input').nth(0).fill(TEST_EMAIL); // Email field
      await page.locator('input').nth(1).fill(TEST_PASSWORD); // Password field
    }

    // Click submit button
    await page.click('button[type="submit"]');

    // Wait for navigation to complete
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
      console.error('   Ensure mock data is seeded and services are running.');
      console.error('   Run: make seed-mock-data');
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
          const retryInputCount = await page.locator('input').count();
          if (retryInputCount >= 2) {
            await page.locator('input').nth(0).fill(TEST_EMAIL);
            await page.locator('input').nth(1).fill(TEST_PASSWORD);
            await page.click('button[type="submit"]');
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
          } else {
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

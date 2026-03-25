# Smoke Tests

Smoke tests are fast, lightweight tests that verify basic functionality and prevent regressions in critical features. They provide rapid feedback during development and continuous integration.

## Overview

Smoke tests validate core application functionality without running full test suites:

- **What are smoke tests?** Quick verification tests that ensure basic features work
- **Why do they exist?** Prevent regressions, provide fast feedback, catch build/runtime failures early
- **Speed requirement:** Must complete in **<2 minutes total**
- **Scope:** Build verification, runtime health checks, API health endpoints, UI page loads

## Running Smoke Tests

### Run All Smoke Tests

```bash
make smoke-test
# or
./tests/smoke/run-all.sh
```

Runs all smoke tests (build, runtime, API, UI) in sequence.

### Run Build Tests Only

```bash
make smoke-test-build
# or
./tests/smoke/build/run.sh
```

Verifies all containers build successfully.

### Run Mobile Smoke Tests

```bash
make smoke-test-mobile
```

For mobile-specific verification (Flutter app build, runtime checks).

### Run UI Tests Only

```bash
npx playwright test tests/smoke/ --reporter=list
```

Runs Playwright UI tests (page loads, login, forms, tabs).

## Test Structure

### Build Tests (`tests/smoke/build/`)

Build smoke tests verify that all containers build successfully and can start without errors.

**Current tests:**
- Container image building for all services
- No dangling dependencies
- Proper Dockerfile configuration

**What it tests:**
- Docker image builds without errors
- All build steps complete successfully
- Base images are correct (Debian 12-slim)
- Service readiness checks pass

### Run Tests (`tests/smoke/run/`)

Runtime smoke tests verify that all services:
- Start successfully
- Stay running (no crash/restart loops)
- Report healthy status
- Accept connections on expected ports

**What it tests:**
- Container health checks pass
- Services don't crash on startup
- API health endpoints respond
- Database connections work

### UI Tests (`tests/smoke/*.spec.ts`)

Playwright-based UI tests for frontend verification.

**Current tests:**
- `pageLoads.spec.ts` - All pages load without JavaScript errors
- `loginPage.spec.ts` - LoginPageBuilder authentication works
- `formModals.spec.ts` - FormModalBuilder modal functionality
- `tabLoads.spec.ts` - Tab navigation works correctly
- `helpers.ts` - Shared test utilities

**What it tests:**
- Pages render without console errors
- Login flow completes successfully
- Form modals open/close properly
- Tab navigation switches content
- GDPR cookie consent works

## Adding New Smoke Tests

### Build Tests

Create a new shell script in `tests/smoke/build/`:

```bash
#!/bin/bash
# tests/smoke/build/test-{service}-{category}.sh

set -e

echo "Testing {service} {category}..."

# Your test logic here
if ! docker build -t {service}:smoke services/{service}/; then
  echo "FAILED: {service} build failed"
  exit 1
fi

echo "PASSED: {service} {category}"
exit 0
```

Naming convention: `test-{service}-{category}.sh`
- Example: `test-flask-backend-build.sh`
- Example: `test-webui-dependencies.sh`

### Runtime Tests

Create a new shell script in `tests/smoke/run/`:

```bash
#!/bin/bash
# tests/smoke/run/test-{service}-{check}.sh

set -e

echo "Testing {service} {check}..."

# Start service in background
docker compose up -d {service-name}

# Wait for service to be ready
sleep 3

# Verify health
if ! curl -sf http://localhost:{port}/health > /dev/null; then
  echo "FAILED: {service} health check failed"
  exit 1
fi

echo "PASSED: {service} {check}"
exit 0
```

Naming convention: `test-{service}-{check}.sh`
- Example: `test-flask-api-health.sh`
- Example: `test-webui-ready.sh`

### UI Tests (Playwright)

Add new tests to `tests/smoke/{feature}.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';
import { login, expectNoConsoleErrors } from './helpers';

test('Feature Name', async ({ page }) => {
  // Login if required
  await login(page);

  // Navigate to feature
  await page.goto('/path/to/feature');

  // Verify functionality
  expect(await page.locator('[data-testid="element"]')).toBeVisible();

  // Check for console errors
  expectNoConsoleErrors(page);
});
```

## Test Requirements

### All Tests Must:

1. **Be executable:** `chmod +x tests/smoke/build/test-*.sh`
2. **Exit with proper codes:**
   - Exit 0 on success
   - Exit non-zero on failure
3. **Complete quickly:** Maximum 30 seconds per test
4. **Provide clear output:**
   ```bash
   echo "PASSED: Description"  # or
   echo "FAILED: Description"
   ```
5. **Fail fast:** Don't continue after first error
6. **Clean up resources:** Stop containers, remove temp files

### Bash Test Template

```bash
#!/bin/bash
# tests/smoke/build/test-example-basic.sh

set -e  # Exit on first error

TEST_NAME="Example Basic Test"

echo "Starting: $TEST_NAME..."

# Your test logic
if [ condition ]; then
  echo "FAILED: $TEST_NAME - Description"
  exit 1
fi

# Success
echo "PASSED: $TEST_NAME"
exit 0
```

### Test Timeout Limits

| Test Type | Timeout |
|-----------|---------|
| Build test | <20 seconds |
| Runtime test | <15 seconds |
| UI test | <30 seconds |
| Total suite | <120 seconds (2 minutes) |

## Pre-Commit Integration

Smoke tests run as **Step 5** in the pre-commit checklist (see `docs/PRE_COMMIT.md`):

1. Linters (flake8, eslint, etc.)
2. Security scans (bandit, gosec, npm audit)
3. Secrets detection
4. Build all containers
5. **Smoke tests** ← You are here
6. Full test suite (unit, integration)
7. Version update
8. Docker base image verification

**Must pass before proceeding to full test suite.**

```bash
# Run pre-commit checklist
./scripts/pre-commit/pre-commit.sh
```

Results logged to: `/tmp/pre-commit-<project>-<epoch>/summary.log`

📚 See [docs/PRE_COMMIT.md](../../docs/PRE_COMMIT.md) for complete pre-commit workflow.

## Troubleshooting

### Port Already in Use

**Problem:** Build/run tests fail with "port already in use"

**Solution:**
```bash
# Stop all containers
docker compose down

# Or kill specific port
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Docker Build Fails

**Problem:** Build tests fail with Docker errors

**Solution:**
```bash
# Check Docker daemon is running
docker ps

# Clean Docker cache if needed
docker system prune -f

# Rebuild without cache
docker build --no-cache -t service:test services/service/
```

### UI Tests Timeout

**Problem:** Playwright tests timeout

**Solution:**
```bash
# Check if dev server is running
curl http://localhost:5173

# Start dev server
make dev

# Run tests with debugging
npx playwright test tests/smoke/ --debug

# Increase timeout in playwright.config.ts if needed
```

### Service Health Check Fails

**Problem:** Runtime tests fail because service isn't ready

**Solution:**
```bash
# Check service logs
docker compose logs {service-name}

# Verify service is actually running
docker compose ps

# Check health endpoint manually
curl http://localhost:{port}/health

# Increase wait time in test if startup is slow
sleep 5  # Increase from 3 to 5
```

### Console Errors in UI Tests

**Problem:** UI tests fail with JavaScript console errors

**Solution:**
- Check browser console for errors: `npx playwright test --ui`
- Fix JavaScript errors in source code
- Add error handling/try-catch blocks
- Check for missing environment variables

### Need to Skip Tests (Not Recommended)

If you absolutely must skip smoke tests temporarily:

```bash
# Skip just smoke tests in pre-commit
export SKIP_SMOKE_TESTS=1
./scripts/pre-commit/pre-commit.sh

# Run pre-commit without smoke tests
./scripts/pre-commit/pre-commit.sh --skip-smoke-tests
```

**Warning:** Always run smoke tests before committing. Skipping them defeats their purpose of catching regressions.

## Best Practices

1. **Keep tests simple:** One thing per test
2. **Fail fast:** Don't wait for timeouts
3. **Clean up:** Always stop containers and remove temp files
4. **Independent:** Tests shouldn't depend on each other
5. **Idempotent:** Running twice produces same result
6. **Isolated:** Don't share state between tests
7. **Clear names:** Test name describes what it tests
8. **Fast feedback:** Especially important during development

## Examples

### Example: Build Test

```bash
#!/bin/bash
# tests/smoke/build/test-flask-backend-build.sh

set -e

echo "Testing Flask backend build..."

if ! docker build -t flask-backend:smoke services/flask-backend/; then
  echo "FAILED: Flask backend build failed"
  exit 1
fi

echo "PASSED: Flask backend builds successfully"
exit 0
```

### Example: Runtime Test

```bash
#!/bin/bash
# tests/smoke/run/test-flask-backend-health.sh

set -e

echo "Testing Flask backend health..."

# Start service
docker compose up -d flask-backend

# Wait for startup
sleep 5

# Check health
if ! curl -sf http://localhost:5000/api/v1/health > /dev/null; then
  echo "FAILED: Flask backend health check failed"
  docker compose logs flask-backend
  exit 1
fi

echo "PASSED: Flask backend is healthy"
exit 0
```

### Example: UI Test (Playwright)

```typescript
// tests/smoke/apiHealth.spec.ts

import { test, expect } from '@playwright/test';

test('API health endpoints respond', async ({ page }) => {
  const endpoints = [
    '/api/v1/health',
    '/api/v1/status',
  ];

  for (const endpoint of endpoints) {
    const response = await page.request.get(`http://localhost:5000${endpoint}`);
    expect(response.status()).toBe(200);
  }
});
```

## References

- 📚 [Testing Guide](../../docs/TESTING.md) - Comprehensive testing documentation
- 📚 [Pre-Commit Checklist](../../docs/PRE_COMMIT.md) - Full pre-commit workflow
- 📚 [Development Guide](../../docs/DEVELOPMENT.md) - Local development setup
- 🔗 [Playwright Documentation](https://playwright.dev/) - UI test framework

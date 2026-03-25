# Testing Guide

Comprehensive testing documentation for the project template, including unit tests, integration tests, smoke tests, mock data, and cross-architecture validation.

## Overview

Testing is organized into multiple levels to ensure comprehensive coverage, fast feedback, and production-ready code:

| Test Level | Purpose | Speed | Coverage |
|-----------|---------|-------|----------|
| **Smoke Tests** | Fast verification of basic functionality | <2 min | Build, run, API health, UI loads |
| **Unit Tests** | Isolated function/method testing | <1 min | Code logic, edge cases |
| **Integration Tests** | Component interaction verification | 1-5 min | Data flow, API contracts |
| **E2E Tests** | Critical workflows end-to-end | 5-10 min | User scenarios, business logic |
| **Performance Tests** | Scalability and throughput validation | 5-15 min | Load, latency, resource usage |

## Mock Data Scripts

### Purpose

Mock data scripts populate the development database with realistic test data, enabling:
- Rapid local development without manual data entry
- Consistent test data across the development team
- Documentation of expected data structure and relationships
- Quick feature iteration with pre-populated databases

### Location & Structure

```
scripts/mock-data/
├── seed-all.py             # Orchestrator: runs all seeders in order
├── seed-users.py           # 3-4 users with different roles/permissions
├── seed-products.py        # 3-4 products with variations/statuses
├── seed-orders.py          # 3-4 orders with different states
├── seed-[feature].py       # Additional feature-specific seeders
└── README.md               # Instructions for running mock data
```

### Naming Convention

- **Python**: `seed-{feature-name}.py`
- **Shell**: `seed-{feature-name}.sh`
- **Organization**: One seeder per logical entity/feature

### Scope: 3-4 Items Per Feature

Each seeder should create **exactly 3-4 representative items** to test all feature variations without creating excessive test data:

**Example (Users)**:
```python
# seed-users.py
items = [
    {"email": "admin@example.com", "role": "admin", "status": "active"},
    {"email": "user@example.com", "role": "user", "status": "active"},
    {"email": "inactive@example.com", "role": "user", "status": "inactive"},
]
```

**Example (Orders)**:
```python
# seed-orders.py
items = [
    {"status": "pending", "amount": 99.99, "customer": "..."},
    {"status": "processing", "amount": 199.99, "customer": "..."},
    {"status": "completed", "amount": 49.99, "customer": "..."},
    {"status": "cancelled", "amount": 299.99, "customer": "..."},
]
```

### Execution

**Seed all test data**:
```bash
make seed-mock-data          # Via Makefile
python scripts/mock-data/seed-all.py  # Direct execution
```

**Seed specific feature**:
```bash
python scripts/mock-data/seed-users.py
python scripts/mock-data/seed-products.py
```

### Implementation Pattern

**Python (PyDAL)**:
```python
#!/usr/bin/env python3
"""Seed mock data for users entity."""

import os
import sys
from dal import DAL

def seed_users():
    db = DAL('sqlite:memory')  # or use DB_TYPE env var

    users = [
        {"email": "admin@example.com", "role": "admin"},
        {"email": "user1@example.com", "role": "user"},
        {"email": "user2@example.com", "role": "user"},
        {"email": "viewer@example.com", "role": "viewer"},
    ]

    for user in users:
        db.users.insert(**user)

    print(f"✓ Seeded {len(users)} users")

if __name__ == "__main__":
    seed_users()
```

**Shell (curl/API)**:
```bash
#!/bin/bash
# seed-products.sh

API_URL="${API_URL:-http://localhost:5000}"
TOKEN="${AUTH_TOKEN}"

# Product 1
curl -X POST "$API_URL/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Product A", "price": 29.99}'

# Product 2
curl -X POST "$API_URL/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Product B", "price": 49.99}'

# Product 3
curl -X POST "$API_URL/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Product C", "price": 99.99}'

# Product 4
curl -X POST "$API_URL/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Product D", "price": 149.99}'

echo "✓ Seeded 4 products"
```

### Makefile Integration

Add to your `Makefile`:

```makefile
.PHONY: seed-mock-data
seed-mock-data:
	@echo "Seeding mock data..."
	@python scripts/mock-data/seed-all.py
	@echo "✓ Mock data seeding complete"

.PHONY: clean-data
clean-data:
	@echo "Clearing mock data..."
	@rm -f data/dev.db
	@echo "✓ Mock data cleared"
```

### When to Create Mock Data Scripts

**Create a mock data script after each new feature/entity completion**:
- After implementing a new user entity → create `seed-users.py`
- After implementing product catalog → create `seed-products.py`
- After implementing order processing → create `seed-orders.py`

This ensures developers can immediately test the feature without manual setup.

---

## Smoke Tests

### Purpose

Smoke tests provide fast verification that basic functionality works after code changes, preventing regressions in core features.

### Requirements (Mandatory)

All projects **MUST** implement smoke tests before committing:

- ✅ **Build Tests**: All containers build successfully without errors
- ✅ **Run Tests**: All containers start and remain healthy
- ✅ **API Health Checks**: All API endpoints respond with 200/healthy status
- ✅ **Page Load Tests**: All web pages load without JavaScript errors
- ✅ **Tab Navigation Tests**: All tabs/routes navigate without console errors

### Location & Structure

```
tests/smoke/
├── build/          # Container build verification
│   ├── test-flask-build.sh
│   ├── test-go-build.sh
│   └── test-webui-build.sh
├── run/            # Container runtime and health
│   ├── test-flask-run.sh
│   ├── test-go-run.sh
│   └── test-webui-run.sh
├── api/            # API health endpoint validation
│   ├── test-flask-health.sh
│   ├── test-go-health.sh
│   └── README.md
├── webui/          # Page load and tab navigation
│   ├── test-pages-load.sh
│   ├── test-tabs-navigate.sh
│   └── README.md
├── run-all.sh      # Execute all smoke tests
└── README.md       # Documentation
```

### Execution

**Run all smoke tests**:
```bash
make smoke-test              # Via Makefile
./tests/smoke/run-all.sh     # Direct execution
```

**Run specific test category**:
```bash
./tests/smoke/build/test-flask-build.sh
./tests/smoke/api/test-flask-health.sh
./tests/smoke/webui/test-pages-load.sh
```

### Speed Requirement

Complete smoke test suite **MUST run in under 2 minutes** to provide fast feedback during development.

### Implementation Examples

**Build Test (Shell)**:
```bash
#!/bin/bash
# tests/smoke/build/test-flask-build.sh

set -e

echo "Testing Flask backend build..."
cd services/flask-backend

# Attempt to build the container
if docker build -t flask-backend:test .; then
    echo "✓ Flask backend builds successfully"
    exit 0
else
    echo "✗ Flask backend build failed"
    exit 1
fi
```

**Health Check Test**:
```bash
#!/bin/bash
# tests/smoke/api/test-flask-health.sh

set -e

echo "Checking Flask API health..."
HEALTH_URL="http://localhost:5000/api/v1/health"

RESPONSE=$(curl -s -w "\n%{http_code}" "$HEALTH_URL")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Flask API is healthy (HTTP $HTTP_CODE)"
    exit 0
else
    echo "✗ Flask API is unhealthy (HTTP $HTTP_CODE)"
    exit 1
fi
```

**Page Load Test (Playwright)**:
```bash
#!/bin/bash
# tests/smoke/webui/test-pages-load.sh

npx playwright test tests/smoke/webui/pages.spec.ts \
  --config=tests/smoke/webui/playwright.config.ts
```

### Pre-Commit Integration

Smoke tests run as part of the pre-commit checklist (step 5) and **must pass before proceeding** to full test suite:

```bash
./scripts/pre-commit/pre-commit.sh
# Step 1: Linters
# Step 2: Security scans
# Step 3: No secrets
# Step 4: Build & Run
# Step 5: Smoke tests ← Must pass
# Step 6: Full tests
```

### Shared Component Smoke Tests (React)

Applications using `@penguintechinc/react-libs` shared components **MUST include Playwright smoke tests** to validate:
- LoginPageBuilder renders and authenticates correctly
- FormModalBuilder opens, validates, and closes properly
- Tab navigation works on multi-tab pages
- All pages load without JavaScript errors

**Test Files Location**:
```
tests/smoke/
├── helpers.ts              # Shared test utilities (login, error collection)
├── pageLoads.spec.ts       # All pages load without JS errors
├── loginPage.spec.ts       # LoginPageBuilder functionality
├── formModals.spec.ts      # FormModalBuilder functionality
├── tabLoads.spec.ts        # Tab navigation on multi-tab pages
├── playwright.config.ts    # Playwright configuration
└── README.md               # Documentation
```

**Running Shared Component Tests**:
```bash
npm run test:smoke              # All smoke tests
npm run test:smoke:ui           # With Playwright UI
npx playwright test tests/smoke/loginPage.spec.ts  # Specific file
```

**Configuration**: Edit the configuration arrays in each test file to match your application's pages, forms, and tabs.

See `tests/smoke/README.md` for detailed configuration and usage instructions.

---

## Unit Tests

### Purpose

Unit tests verify individual functions and methods in isolation with mocked dependencies.

### Location

```
tests/unit/
├── flask-backend/
│   ├── test_auth.py
│   ├── test_models.py
│   └── test_api.py
├── go-backend/
│   ├── auth_test.go
│   ├── models_test.go
│   └── api_test.go
└── webui/
    ├── components/
    │   └── Button.test.tsx
    └── utils/
        └── helpers.test.ts
```

### Execution

```bash
make test-unit              # All unit tests
pytest tests/unit/          # Python
go test ./...               # Go
npm test                    # JavaScript/TypeScript
```

### Requirements

- All dependencies must be mocked
- Network calls must be stubbed
- Database access must be isolated
- Tests must run in parallel when possible

---

## Integration Tests

### Purpose

Integration tests verify that components work together correctly, including real database interactions and service communication.

### Location

```
tests/integration/
├── flask-backend/
│   ├── test_auth_flow.py
│   ├── test_user_creation.py
│   └── test_api_contracts.py
├── services/
│   ├── test_service_communication.py
│   └── test_data_pipeline.py
└── database/
    ├── test_migrations.py
    └── test_queries.py
```

### Execution

```bash
make test-integration       # All integration tests
pytest tests/integration/   # Python
go test -tags=integration ./...  # Go
npm run test:integration    # JavaScript
```

### Requirements

- Use real databases (test instances)
- Test complete workflows
- Verify API contracts
- Test error scenarios

---

## End-to-End Tests

### Purpose

E2E tests verify critical user workflows from start to finish, testing the entire application stack.

### Location

```
tests/e2e/
├── critical-workflows.spec.ts
├── user-registration.spec.ts
├── order-processing.spec.ts
└── authentication.spec.ts
```

### Execution

```bash
make test-e2e               # All E2E tests
npx playwright test tests/e2e/  # Playwright
```

---

## Performance Tests

### Purpose

Performance tests validate scalability, throughput, and resource usage under load.

### Location

```
tests/performance/
├── load-test.js
├── stress-test.js
└── profile-report.md
```

### Execution

```bash
make test-performance
npm run test:performance
```

---

## Cross-Architecture Testing

### Purpose

Cross-architecture testing ensures the application builds and runs correctly on both amd64 and arm64 architectures, preventing platform-specific bugs.

### When to Test

**Before every final commit**, test on the alternate architecture:
- Developing on amd64 → Build and test arm64 with QEMU
- Developing on arm64 → Build and test amd64 with QEMU

### Setup (First Time)

Enable Docker buildx for multi-architecture builds:

```bash
docker buildx create --name multiarch --driver docker-container
docker buildx use multiarch
```

### Single Architecture Build

```bash
# Test current architecture (native, fast)
docker build -t flask-backend:test services/flask-backend/

# Or explicitly specify architecture
docker build --platform linux/amd64 -t flask-backend:test services/flask-backend/
```

### Cross-Architecture Build (QEMU)

```bash
# Test alternate architecture (uses QEMU emulation)
docker buildx build --platform linux/arm64 -t flask-backend:test services/flask-backend/

# Or test both simultaneously
docker buildx build --platform linux/amd64,linux/arm64 -t flask-backend:test services/flask-backend/
```

### Multi-Architecture Build Script

Create `scripts/build/test-multiarch.sh`:

```bash
#!/bin/bash
# Test both architectures before commit

set -e

SERVICES=("flask-backend" "go-backend" "webui")
ARCHITECTURES=("linux/amd64" "linux/arm64")

for service in "${SERVICES[@]}"; do
    echo "Testing $service on multiple architectures..."

    for arch in "${ARCHITECTURES[@]}"; do
        echo "  → Building for $arch..."
        docker buildx build \
            --platform "$arch" \
            -t "$service:multiarch-test" \
            "services/$service/" || {
            echo "✗ Build failed for $service on $arch"
            exit 1
        }
    done

    echo "✓ $service builds successfully on amd64 and arm64"
done

echo "✓ All services passed multi-architecture testing"
```

### Makefile Integration

```makefile
.PHONY: test-multiarch
test-multiarch:
	@echo "Testing multi-architecture builds..."
	@bash scripts/build/test-multiarch.sh

.PHONY: build-multiarch
build-multiarch:
	@docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-t $(IMAGE_NAME):$(VERSION) \
		--push .
```

### Pre-Commit Integration

Add to pre-commit script (before final commit):

```bash
# Step 8: Cross-architecture testing
if [ "$ENABLE_QEMU_TEST" = "true" ]; then
    echo "Testing cross-architecture builds with QEMU..."
    make test-multiarch || exit 1
fi
```

### Troubleshooting

**QEMU not available**:
```bash
# Install QEMU support
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

**Slow builds with QEMU**:
- Expect 2-5x slower builds when using QEMU emulation
- Use for final validation, not every iteration
- Consider caching intermediate layers

**Architecture-specific issues**:
- File path separators (Windows vs Linux)
- Endianness in binary protocols
- Floating-point precision
- Package availability

---

## Test Execution Order (Pre-Commit)

Follow this order for efficient testing before commits:

1. **Linters** (fast, <1 min)
2. **Security scans** (fast, <1 min)
3. **Secrets check** (fast, <1 min)
4. **Build & Run** (5-10 min)
5. **Smoke tests** (fast, <2 min) ← Gates further testing
6. **Unit tests** (1-2 min)
7. **Integration tests** (2-5 min)
8. **E2E tests** (5-10 min)
9. **Cross-architecture build** (optional, slow)

## CI/CD Integration

All tests run automatically in GitHub Actions:

- **On PR**: Smoke + Unit + Integration tests
- **On main merge**: All tests + Performance tests
- **Nightly**: Performance + Cross-architecture tests
- **Release**: Full suite + Manual sign-off

See [Workflows](WORKFLOWS.md) for detailed CI/CD configuration.

---

**Last Updated**: 2026-01-06
**Maintained by**: Penguin Tech Inc

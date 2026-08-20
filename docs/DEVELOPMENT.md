# Local Development Guide

Complete guide to setting up a local development environment, running the application locally, and following the development workflow including testing and pre-commit checks.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Starting Development Environment](#starting-development-environment)
4. [Development Workflow](#development-workflow)
5. [Common Tasks](#common-tasks)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **macOS 12+**, **Linux (Ubuntu 20.04+)**, or **Windows 10+ with WSL2**
- **Docker Desktop** 4.0+ (or Docker Engine 20.10+)
- **Docker Compose** 2.0+
- **Git** 2.30+
- **Python** 3.13+ (for Python service development)
- **Node.js** 18+ (for WebUI development)
- **Go** 1.24.2+ (if working on Go services; 1.23.x acceptable as fallback if needed)

### Optional Tools

- **Docker Buildx** (for multi-architecture builds)
- **Helm** (for Kubernetes deployments)
- **kubectl** (for Kubernetes clusters)

### Installation

**macOS (Homebrew)**:
```bash
brew install docker docker-compose git python node go
brew install --cask docker
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git python3.13 nodejs golang-1.24
sudo usermod -aG docker $USER  # Allow docker without sudo
newgrp docker                   # Activate group change
```

**Verify Installation**:
```bash
docker --version      # Docker 20.10+
docker-compose --version  # Docker Compose 2.0+
git --version
python3 --version     # Python 3.13+
node --version        # Node.js 18+
```

---

## Initial Setup

### Clone Repository

```bash
git clone <repository-url>
cd project-name
```

### Install Dependencies

```bash
# Install all project dependencies
make setup
```

This runs:
1. Python environment setup (venv, requirements)
2. Node.js dependency installation (npm install)
3. Go module setup (go mod download)
4. Pre-commit hooks installation
5. Database initialization

### Environment Configuration

Copy and customize environment files:

```bash
# Copy example environment files
cp .env.example .env
cp .env.local.example .env.local  # Optional: local overrides
```

**Key Environment Variables**:
```bash
# Database
DB_TYPE=postgresql          # postgres, mysql, mariadb, sqlite
DB_HOST=localhost
DB_PORT=5432
DB_NAME=project_dev
DB_USER=postgres
DB_PASSWORD=postgres

# Flask Backend
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key-for-dev

# License (Development - all features available)
RELEASE_MODE=false
LICENSE_KEY=not-required-in-dev

# Port Configuration
FLASK_PORT=5000
GO_PORT=8000
WEBUI_PORT=3000
REDIS_PORT=6379
```

**`SECRET_KEY` is required outside `TESTING`** — `create_app()` now raises
`RuntimeError` at startup if it is left at the public placeholder default
committed in `app/config.py`. Quart signs the session cookie with
`SECRET_KEY`, and `app/oauth.py`'s `oauth_state` CSRF check lives entirely
inside that signed session, so a known key is as forgeable as no signature
at all. `docker-compose.yml` no longer supplies a fallback for it
(`${SECRET_KEY:?...}`) — set a real value in `.env` as shown above before
running `docker compose up`. The test suite is unaffected: `TestingConfig`
sets `TESTING=true`, which is the one carve-out, mirroring
`app/encryption.py`'s `ENCRYPTION_KEY` check.

### Health Cache (Valkey/Redis) — `portal-api`

`app/health_poller.py`'s background health sweep (`GET /api/v1/products/health`)
writes through `app/health_cache.py` to a shared Valkey/Redis-protocol store, so
every worker/pod sees the same cached status. The variables it reads:

```bash
CACHE_HOST=            # unset (default) = no shared cache; see below
CACHE_PORT=6379
CACHE_DB=0
CACHE_PASS=
CACHE_SSL=false
```

**`REDIS_URL` is NOT read by this code.** `docker-compose.yml`'s `portal-api`
service sets `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0` for a
different, older integration path — setting only `REDIS_URL` and expecting
the health cache to be shared is the trap this note exists to prevent. Set
`CACHE_HOST` (at minimum) explicitly.

**Unset `CACHE_HOST` is a supported, not a broken, state** — the poller
degrades to a per-process in-memory fallback (Task 6 requirement 4) rather
than crashing or losing data. The service logs an unmistakable WARNING at
startup when this is the case (`health_cache_is_per_process_only`), because
the practical consequence is easy to miss otherwise: `GET
/api/v1/products/health` then returns each worker's OWN last-observed
status rather than a value shared across workers or replicas — two requests
that happen to land on different pods can disagree about the same
connection's health. Set `CACHE_HOST` (pointing at a Valkey instance --
`valkey/valkey:8-bookworm`, the org standard; see devops-containers.md) to
get the shared-cache behaviour the brief describes. No `k8s/helm/portal-api`
values currently wire this up — `k8s/helm/portal-api/` is still a stub
(`templates/_helpers.tpl` only); Phase 7 owns authoring the chart, including
a `CACHE_HOST` default pointing at wherever it deploys Valkey.

**Prometheus metrics** (`app/health_poller.py`) are served on `:9090`,
separate from the API's `:8000` (see `services/portal-api/Dockerfile`'s
`EXPOSE`). Nothing in this repo currently scrapes it —
`infrastructure/monitoring/prometheus/`, which `docker-compose.yml` mounts a
config from, does not exist as a directory. The port is real and open; a
Prometheus server pointed at it will work, but none is wired up yet.

### JWT Signing Keystore — `portal-api`

`app/__init__.py`'s `_build_oidc_provider` picks the penguin-aaa `KeyStore`
backing every token this service issues and verifies. The variables it
reads:

```bash
JWT_KEYSTORE_PATH=       # unset (default) = in-process key; see below
DEPLOYMENT_REPLICAS=1    # how many replicas the operator/chart intends
```

**Unset `JWT_KEYSTORE_PATH` with `DEPLOYMENT_REPLICAS=1` is a supported,
not a broken, state** — the service falls back to an in-process
`MemoryKeyStore` rather than crashing, the same "degrade, don't crash"
shape as the health cache above. It logs an unmistakable WARNING at
startup when this is the case (`jwt_keystore_is_per_process_only`),
because the consequence is a genuine security-relevant behaviour change,
not just staleness: the signing key is lost on every restart, and a token
minted by a *different* process — another replica, or a previous run of
this one — is rejected as an **invalid signature**, not as expired. This
is fine for a single dev process or the test suite; it is never fine for
more than one replica of the same deployment.

**Unset `JWT_KEYSTORE_PATH` with `DEPLOYMENT_REPLICAS` > 1 refuses to
start.** This is the fix for the actual defect that motivated this
section: prior to it, every replica silently built its own
`MemoryKeyStore`, so a token minted by pod A failed verification on pod B
with a plain `401 Invalid token - key not found` — intermittent,
load-balancer-routing-dependent, and invisible against a single pod,
which is exactly the failure mode `devops-kubernetes.md`'s 3+-replica
production requirement walks straight into if this were left as a silent
fallback. The service now raises `RuntimeError` at boot instead, naming
the fix in the error message.

**`DEPLOYMENT_REPLICAS` is declared, not detected.** Kubernetes gives a
pod no reliable in-process signal for "how many siblings does my
ReplicaSet have" — the Downward API exposes this pod's own identity, never
the replica count — so guessing was rejected in favour of an explicit
value the chart is expected to set from its own `replicaCount`, the same
way `CACHE_HOST` above is a deliberate declaration rather than an
auto-detected shared store.

**Getting a real shared keystore in place is chart/ops work, not
something this service can do for itself**, and is NOT yet wired up —
`k8s/helm/portal-api/` is still a stub (`templates/_helpers.tpl` only), so
today setting `DEPLOYMENT_REPLICAS` > 1 without also standing up a shared
`JWT_KEYSTORE_PATH` is a deliberate, correct refusal to start, not a gap
in this fix. Two provisioning shapes are worth naming for whoever picks
that up:

* **A pre-populated, read-only Secret volume** (Vault Agent Injector,
  External Secrets Operator, or a one-time `kubectl create secret generic`
  from a manually generated keypair), mounted at the same
  `JWT_KEYSTORE_PATH` in every replica, containing `FileKeyStore`'s own
  JSON shape (`{"keys": [{"kid": ..., "pem": ...}, ...]}`). Nothing in
  this codebase currently calls `KeyStore.rotate_key()`, so
  `FileKeyStore.__init__` never writes to a path that already has content
  — it only calls `_save()` when the file does not yet exist. A
  pre-populated Secret is therefore read-only in practice: no
  `ReadWriteMany` PVC needed (a Secret volume is a per-node projection,
  not a PVC, and mounts fine under `readOnlyRootFilesystem: true`), and no
  write race between replicas. This is the preferred shape —
  `security.md`/`general.md` route secret material through
  Vault/Sealed-Secrets/External-Secrets-Operator, not a shared filesystem,
  and this avoids inventing a new `KeyStore` implementation to get there.
* **A shared `ReadWriteMany` PVC that `FileKeyStore` self-bootstraps on
  first boot** works too, but has a real race: if two replicas start
  concurrently against an *empty* shared path, both see the file missing,
  both generate their own key, and both call `_save()` — the file ends up
  holding whichever replica wrote last, while the other keeps signing
  with a key that is no longer on disk. This is the same class of defect
  this section exists to close, just moved from "every boot" to "the
  first concurrent rollout." If this shape is used, the file must be
  provisioned (e.g. by a Helm pre-install/pre-upgrade hook Job) *before*
  any replica of the Deployment starts, never left for the app to
  self-generate under a live multi-replica rollout.

### Database Initialization

```bash
# Create database and run migrations
make db-init

# Seed with mock data (3-4 items per entity)
make seed-mock-data

# Verify database connection
make db-health
```

---

## Starting Development Environment

### Quick Start (All Services)

```bash
# Start all services in one command
make dev

# This runs:
# - PostgreSQL database
# - Redis cache
# - Flask backend (port 5000)
# - Go backend (port 8000)
# - Node.js WebUI (port 3000)

# Access the application:
# Web UI:      http://localhost:3000
# Flask API:   http://localhost:5000
# Go API:      http://localhost:8000
# Adminer:     http://localhost:8080 (database UI)
```

### Individual Service Management

**Start specific services**:
```bash
# Start only Flask backend
docker-compose up -d portal-api

# Start WebUI and database
docker-compose up -d postgres webui

# Start without detaching (see logs)
docker-compose up portal-api
```

**View service logs**:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f portal-api

# Last 100 lines, follow new entries
docker-compose logs -f --tail=100 webui
```

**Stop services**:
```bash
# Stop all services (keep data)
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Restart services
docker-compose restart

# Rebuild and restart (apply code changes)
docker-compose down && docker-compose up -d --build
```

### Development Docker Compose Files

- **`docker-compose.dev.yml`**: Local development (hot-reload, debug ports, fake SMTP)
- **`docker-compose.yml`**: Production-like (health checks, resource limits, no debug)

Use dev version locally:
```bash
docker-compose -f docker-compose.dev.yml up
```

---

## Development Workflow

### 1. Start Development Environment

```bash
make dev        # Start all services
make seed-data  # Populate with test data
```

### 2. Make Code Changes

Edit files in your favorite editor. Services auto-reload:

- **Python (Flask)**: Reload on file save (FLASK_DEBUG=1)
- **Node.js (React)**: Hot reload (Webpack dev server)

### 3. Verify Changes

```bash
# Quick smoke tests
make smoke-test

# Run linters
make lint

# Run unit tests (specific service)
cd services/portal-api && pytest tests/unit/

# Run all tests
make test
```

### 4. Populate Mock Data for Feature Testing

After implementing a new feature, create mock data scripts:

```bash
# Create mock data script (e.g., for new "Products" feature)
cat > scripts/mock-data/seed-products.py << 'EOF'
from dal import DAL

def seed_products():
    db = DAL('postgresql://user:password@localhost/dbname')

    products = [
        {"name": "Product A", "price": 29.99, "status": "active"},
        {"name": "Product B", "price": 49.99, "status": "active"},
        {"name": "Product C", "price": 99.99, "status": "inactive"},
        {"name": "Product D", "price": 149.99, "status": "active"},
    ]

    for product in products:
        db.products.insert(**product)

    print(f"✓ Seeded {len(products)} products")

if __name__ == "__main__":
    seed_products()
EOF

# Run the mock data script
python scripts/mock-data/seed-products.py

# Add to seed-all.py orchestrator
echo "from seed_products import seed_products; seed_products()" >> scripts/mock-data/seed-all.py
```

📚 **Complete Mock Data Guide**: [Testing Documentation - Mock Data Scripts](TESTING.md#mock-data-scripts)

### 4.5 Database Migrations with Alembic

When adding new database tables or modifying schemas, use Alembic:

**Workflow**:
```bash
# 1. Define SQLAlchemy models in services/portal-api/app/models.py
#    (See docs/standards/DATABASE.md for examples)

# 2. Generate migration script
cd services/portal-api
alembic revision --autogenerate -m "Add teams table"

# 3. Review migration in alembic/versions/
#    Inspect the generated migration file and make edits if needed

# 4. Apply migration to local database
alembic upgrade head

# 5. Restart Flask service to pick up schema changes
docker-compose up -d --build portal-api

# 6. Verify migration applied
alembic history  # View migration history
alembic current  # Check current migration version
```

**Key Points**:
- Always review auto-generated migrations before applying
- Keep migration files in git history
- Test migrations on all supported DB types (PostgreSQL, MySQL, SQLite)
- Document complex migrations with comments
- For rollback: `alembic downgrade -1`

📚 **Alembic Documentation**: [Database Standards](docs/standards/DATABASE.md)

### 5. Run Pre-Commit Checklist

Before committing, run the comprehensive pre-commit script:

```bash
./scripts/pre-commit/pre-commit.sh
```

**Steps**:
1. ✅ Linters (flake8, black, eslint, golangci-lint, etc.)
2. ✅ Security scans (bandit, npm audit, gosec)
3. ✅ Secret detection (no API keys, passwords, tokens)
4. ✅ Build & Run (build all containers, verify runtime)
5. ✅ Smoke tests (build, health checks, UI loads)
6. ✅ Unit tests (isolated component testing)
7. ✅ Integration tests (component interactions)
8. ✅ Version update & Docker standards

**Troubleshooting Pre-Commit**:

See [Pre-Commit Documentation](PRE_COMMIT.md) for detailed guidance on:
- Fixing linting errors
- Resolving security vulnerabilities
- Excluding files from checks
- Bypassing specific checks (with justification)

### 6. Testing & Validation

Comprehensive testing guide:

📚 **Complete Testing Guide**: [Testing Documentation](TESTING.md)

**Quick Test Commands**:
```bash
# Smoke tests only (fast, <2 min)
make smoke-test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# All tests
make test

# Specific test file
pytest tests/unit/test_auth.py

# Cross-architecture testing (QEMU)
make test-multiarch
```

#### Isolated test venv (`make test-api`)

`tests/` (root pytest suite, mostly `tests/api/`) imports `penguin-dal`,
`penguin-aaa`, and friends. If your global/user `pip` has any of these
installed **editable** — `pip install -e ~/code/penguin-libs/packages/...`,
common when working on `penguin-libs` itself — the suite's pass/fail no
longer depends on this repo's code, it depends on whichever branch/commit
that sibling checkout happens to be sitting on. An editable `penguin-dal`
missing a method the released version has (or vice versa) silently changes
the test count with no code change here at all.

`make test-api` avoids this entirely: it builds a project-local venv
(`.venv/`, gitignored) from **only** `services/portal-api/requirements.txt`
via `pip install --require-hashes`, then runs `pytest tests/ -q` through
that venv's interpreter. Nothing in `.venv/` can reference a path outside
this repo — hash verification fails the install outright if it tried. This
is exactly what CI installs, so a green `make test-api` locally means the
same thing a green CI run means.

```bash
make venv-portal-api   # create/refresh .venv/ (idempotent — no-op if
                        # services/portal-api/requirements.txt is unchanged
                        # since the last install)
make test-api          # venv-portal-api, then pytest tests/ -q through it
```

`test-api-live` (product-checkout-required mode) now runs through the same
venv. Refresh whenever `services/portal-api/requirements.in` changes:
regenerate the lock with
`uv pip compile services/portal-api/requirements.in --generate-hashes -o services/portal-api/requirements.txt`,
then `make venv-portal-api` picks up the new hash automatically (it keys
its no-op check off `requirements.txt`'s own sha256, not a manual flag).

The pre-commit **mypy** hook resolves through the same `.venv` now too
(`scripts/hooks/run-mypy.sh`), not the ambient/system `mypy` on `PATH`. It
used to be `language: system`, which imports `penguin_dal` off whatever an
editable `~/code/penguin-libs` checkout happens to be — a branch that
drifts independently of this repo and can disagree with the pinned release
about what needs a `# type: ignore`. If `.venv/` doesn't exist yet, run
`make venv-portal-api` once; the hook fails with that instruction rather
than silently falling back to the ambient environment.

This repo has exactly one Python requirements set —
`services/portal-api/requirements.txt`. A pre-portal-api root
`requirements.{in,txt}` (py4web/pydal, pinning the forbidden `gunicorn`)
existed until this was cleaned up; nothing imported it, and it also made
`pip-audit` unresolvable (`greenlet` arrives unpinned via `sqlalchemy`,
which `--require-hashes` can't handle). Do not recreate a root-level
requirements set — add new dependencies to `services/portal-api/`.

`tests/api/test_nest_adapter.py::TestAgainstLiveNest` executes Nest's own
Quart app from a sibling `~/code/nest` checkout and needs Nest's own
`opentelemetry` SDK/exporter stack (`apps/api/telemetry.py`) to do it — the
portal deliberately does NOT declare `opentelemetry` for itself just to run
this cross-repo suite; it isn't a portal-api dependency and installing just
the top-level package (enough to pass an `importorskip`) would still blow
up deeper inside Nest's `configure_telemetry()`, trading a clean skip for a
confusing failure. These 8 tests skip under plain `make test-api` (no
checkout, or the checkout's own deps missing) and now genuinely FAIL rather
than silently skip under `make test-api-live`
(`REQUIRE_PRODUCT_SOURCE=1`) if the checkout is present but its
dependencies aren't — see `_require_or_skip` in that file.

### 7. Create Pull Request

Once tests pass:

```bash
# Push branch
git push origin feature-branch-name

# Create PR via GitHub CLI
gh pr create --title "Brief feature description" \
  --body "Detailed description of changes"

# Or use web UI: https://github.com/your-org/repo/compare
```

### 8. Code Review & Merge

- Address review feedback
- Re-run tests if changes made
- Merge when approved

---

## Common Tasks

### Adding a New Python Dependency

```bash
# Add to services/portal-api/requirements.txt
echo "new-package==1.0.0" >> services/portal-api/requirements.txt

# Rebuild Flask container
docker-compose up -d --build portal-api

# Verify import works
docker-compose exec portal-api python -c "import new_package"
```

### Adding a New Node.js Dependency

```bash
# Add to services/webui/package.json
npm install new-package

# Rebuild WebUI container
docker-compose up -d --build webui

# Verify in running container
docker-compose exec webui npm list new-package
```

### Adding a New Environment Variable

```bash
# Add to .env
echo "NEW_VAR=value" >> .env

# Restart services to pick up new variable
docker-compose restart

# Verify it's set
docker-compose exec portal-api printenv | grep NEW_VAR
```

### Debugging a Service

**View logs in real-time**:
```bash
docker-compose logs -f portal-api
```

**Access container shell**:
```bash
# Python service
docker-compose exec portal-api bash

# Node.js service
docker-compose exec webui bash
```

**Execute commands in container**:
```bash
# Run Python script
docker-compose exec portal-api python -c "print('hello')"

# Check service health
docker-compose exec portal-api curl http://localhost:5000/health
```

### Database Operations

**Connect to database**:
```bash
# PostgreSQL
docker-compose exec postgres psql -U postgres -d project_dev

# MySQL
docker-compose exec mysql mysql -u root -p

# View schema
\dt                    # PostgreSQL tables
SHOW TABLES;           # MySQL tables
```

**Reset database**:
```bash
# Full reset (deletes all data)
docker-compose down -v
make db-init
make seed-mock-data
```

**Run migrations**:
```bash
# Auto-migrate on startup
docker-compose restart portal-api

# Or manually run migration
docker-compose exec portal-api python -m migrations
```

### Working with Git Branches

```bash
# Create feature branch
git checkout -b feature/new-feature-name

# Keep branch updated with main
git fetch origin
git rebase origin/main

# Clean commit history before PR
git rebase -i origin/main  # Interactive rebase

# Push branch
git push origin feature/new-feature-name
```

### Database Backups

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U postgres project_dev > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U postgres project_dev < backup.sql

# Backup SQLite
docker cp project_dev:/data/app.db ./app.db.backup
```

---

## Troubleshooting

### Services Won't Start

**Check if ports are already in use**:
```bash
# Find what's using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or use different ports in .env
FLASK_PORT=5001
```

**Docker daemon not running**:
```bash
# macOS
open /Applications/Docker.app

# Linux
sudo systemctl start docker

# Windows (Docker Desktop)
# Start Docker Desktop from Applications
```

### Database Connection Error

```bash
# Verify database container is running
docker-compose ps postgres

# Check database credentials in .env
cat .env | grep DB_

# Connect to database directly
docker-compose exec postgres psql -U postgres -d postgres

# View logs
docker-compose logs postgres
```

### Flask Backend Won't Start

```bash
# Check logs
docker-compose logs portal-api

# Verify database migration
docker-compose exec portal-api python -c "from app import db; db.create_all()"

# Reset and rebuild
docker-compose down
docker-compose up -d --build portal-api
```

### Smoke Tests Failing

**Check which test failed**:
```bash
# Run individually
./tests/smoke/build/test-flask-build.sh
./tests/smoke/api/test-flask-health.sh
./tests/smoke/webui/test-pages-load.sh
```

**Common issues**:
- Service not healthy (logs: `docker-compose logs <service>`)
- Port not exposed (check docker-compose.yml)
- API endpoint not implemented
- Missing environment variables

See [Testing Documentation - Smoke Tests](TESTING.md#smoke-tests) for detailed troubleshooting.

### Git Merge Conflicts

```bash
# View conflicts
git status

# Edit conflicted files (marked with <<<<, ====, >>>>)
# Remove conflict markers and keep desired code

# Mark as resolved
git add <resolved-file>

# Complete merge
git commit -m "Resolve merge conflicts"
```

### Slow Docker Builds

```bash
# Check Docker disk usage
docker system df

# Clean up unused images/containers
docker system prune

# Rebuild without cache (slow, but fresh)
docker-compose build --no-cache portal-api
```

### QEMU Cross-Architecture Build Issues

**QEMU not available**:
```bash
# Install QEMU support
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Verify buildx setup
docker buildx ls
```

**Slow arm64 build with QEMU**:
```bash
# Expected: 2-5x slower with QEMU emulation
# Use only for final validation, not every iteration

# Build native architecture (fast)
docker buildx build --load .

# Build alternate with QEMU (slow)
docker buildx build --platform linux/arm64 .
```

See [Testing Documentation - Cross-Architecture Testing](TESTING.md#cross-architecture-testing) for complete details.

---

## Tips & Best Practices

### Hot Reload Development

For fastest iteration:
```bash
# Start services once
docker-compose up -d

# Edit Python files → auto-reload (FLASK_DEBUG=1)
# Edit JavaScript files → hot reload (Webpack)
# Edit Go files → restart service
```

### Environment-Specific Configuration

```bash
# Development settings (auto-loaded)
.env              # Default development config
.env.local        # Local machine overrides (gitignored)

# Production settings (via secret management)
Kubernetes secrets
AWS Secrets Manager
HashiCorp Vault
```

### Code Organization

Keep project clean:
```bash
# Remove old branches
git branch -D old-branch

# Clean local Docker images
docker image prune -a

# Clean unused containers
docker container prune
```

### Performance Tips

```bash
# Use specific services to reduce memory usage
docker-compose up postgres portal-api  # Skip Go backend, WebUI

# Use lightweight testing
make smoke-test  # Instead of full test suite while developing

# Cache Docker layers by building in order of frequency of change
Dockerfile: base → dependencies → code → entrypoint
```

---

## Related Documentation

- **Testing**: [Testing Documentation](TESTING.md)
  - Mock data scripts
  - Smoke tests
  - Unit/integration/E2E tests
  - Performance tests
  - Cross-architecture testing

- **Pre-Commit**: [Pre-Commit Checklist](PRE_COMMIT.md)
  - Linting requirements
  - Security scanning
  - Build verification
  - Test requirements

- **Deployment**: [Deployment Guide](deployment/)
  - Containerization
  - Kubernetes deployment
  - Docker Compose production
  - Health checks

- **Standards**: [Development Standards](STANDARDS.md)
  - Architecture decisions
  - Code style
  - API conventions
  - Database patterns

- **Workflows**: [CI/CD Workflows](WORKFLOWS.md)
  - GitHub Actions pipelines
  - Build automation
  - Test automation
  - Release processes

---

**Last Updated**: 2026-01-06
**Maintained by**: Penguin Tech Inc

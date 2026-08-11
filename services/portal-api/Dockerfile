# Quart Backend Dockerfile
# Multi-stage build for production

FROM python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS builder

WORKDIR /app

# Install build dependencies for asyncpg and other C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential=12.9 \
    libpq-dev=15.18-0+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install dependencies with uv and hash verification
RUN pip install --no-cache-dir --upgrade \
    'uv>=1.0.0' && \
    uv pip install --system --require-hashes -r requirements.txt

# Production stage
FROM python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS runtime

WORKDIR /app

# Install runtime dependencies only. Explicit numeric UID/GID (1000) rather
# than an unqualified name: matches devops-kubernetes.md's securityContext
# (runAsUser: 1000) and resolves on host systems that can't look a named
# user up (hadolint DL3066).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5=15.18-0+deb12u1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r -g 1000 appuser && useradd -r -u 1000 -g appuser appuser

# Copy python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages \
     /usr/local/lib/python3.13/site-packages

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER 1000

# Environment variables
# Container binds all interfaces by design (it's the only process in its
# network namespace); Quart reads from HOST/PORT env vars.
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports: 8000 the API, 9090 Prometheus metrics (health poller --
# app/health_poller.py start_metrics_server, a separate listener from the
# authenticated API port so a default unauthenticated scrape still works).
EXPOSE 8000
EXPOSE 9090

# Health check (native Python, no curl needed). JSON/exec form: no shell,
# so an uncaught exception from http.client (e.g. connection refused)
# already exits non-zero on its own -- there was never a code path where a
# trailing shell `|| exit 1` did anything the script's own exit() did not.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import http.client; c = http.client.HTTPConnection('localhost', 8000); c.request('GET', '/healthz'); exit(0 if c.getresponse().status == 200 else 1)"]

# Run with hypercorn (async ASGI server for Quart)
CMD ["hypercorn", "--bind", "0.0.0.0:8000", "--workers", "1", \
     "app:create_app()"]

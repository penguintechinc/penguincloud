# WebUI Dockerfile
# Node.js backend + React frontend shell

# Build stage
FROM node:26-bookworm-slim@sha256:cd565714d4da3e84bfd341e31448f81d47c6362198f152345297c9c1154e6341 AS builder

WORKDIR /app

# @penguintechinc/react-libs is a normal npm dependency (package.json,
# public npm registry per backend.md) installed by `npm ci` below -- there
# is no local shared/react_libs tree in this repo to vendor in.

# Copy package files
COPY ./services/webui/package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY ./services/webui .

# Build the application
RUN npm run build

# Production stage
FROM node:26-bookworm-slim@sha256:cd565714d4da3e84bfd341e31448f81d47c6362198f152345297c9c1154e6341 AS production

WORKDIR /app

# node:26-bookworm-slim ships a non-root `node` user at UID/GID 1000 (same
# as 22-bookworm-slim -- re-verified via `docker run --rm <img> id node`
# when bumping the base) -- reused rather than creating a second one
# (groupadd/useradd at GID 1000 collides with it: "GID '1000' already
# exists"). Numeric UID matches services/portal-api/Dockerfile and
# devops-kubernetes.md's securityContext (runAsUser: 1000).

# Copy package files for production dependencies
COPY ./services/webui/package*.json ./

# Install production dependencies only (lockfileVersion 3 supports omit)
RUN npm ci --omit=dev && npm cache clean --force

# Copy built assets from builder
COPY --from=builder /app/dist ./dist

# Set ownership
RUN chown -R node:node /app

# Switch to non-root user. Numeric form matches portal-api's Dockerfile.
USER 1000

# Environment defaults
ENV NODE_ENV=production \
    PORT=3000 \
    FLASK_API_URL=http://portal-api:5000

# Expose port
EXPOSE 3000

# Health check (JSON/exec form -- no shell, matches portal-api's Dockerfile;
# also what hadolint DL3025 wants for CMD/HEALTHCHECK arguments)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["node", "-e", "require('http').get('http://localhost:3000/healthz', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"]

# Run the server
CMD ["node", "dist/server/index.js"]

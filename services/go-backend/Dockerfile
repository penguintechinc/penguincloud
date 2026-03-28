# Go Backend Dockerfile
# High-performance backend with XDP/AF_XDP and NUMA support

# Build stage
FROM golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder

WORKDIR /app

# Install build dependencies for eBPF/XDP
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang \
    llvm \
    libbpf-dev \
    linux-headers-generic \
    && rm -rf /var/lib/apt/lists/*

# Copy go module files first for better caching
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo \
    -ldflags="-w -s" \
    -o /app/server ./cmd/server

# Production stage
FROM debian:bookworm-slim@sha256:f06537653ac770703bc45b4b113475bd402f451e85223f0f2837acbf89ab020a

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libbpf1 \
    numactl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (note: XDP operations may require root)
RUN groupadd -r gobackend && useradd -r -g gobackend gobackend

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/server .

# Set ownership
RUN chown -R gobackend:gobackend /app

# Note: For XDP operations, container must run with:
#   --privileged or --cap-add=NET_ADMIN --cap-add=SYS_ADMIN --cap-add=IPC_LOCK
# If not using XDP features, can run as non-root:
# USER gobackend

# Environment defaults
ENV GO_ENV=production \
    HOST=0.0.0.0 \
    PORT=8080 \
    NUMA_ENABLED=false \
    XDP_ENABLED=false \
    XDP_MODE=skb \
    XDP_INTERFACE=eth0 \
    MEMORY_POOL_SLOTS=1024 \
    MEMORY_POOL_SLOT_SIZE=2048

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q --spider http://localhost:8080/healthz || exit 1

# Run the server
CMD ["./server"]

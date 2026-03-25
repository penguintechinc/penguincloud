# MarchProxy Configuration

This directory contains MarchProxy-compatible configuration files for importing this application's services into MarchProxy API Gateway.

## Files

| File | Purpose |
|------|---------|
| `services.json` | Service definitions (backends) |
| `mappings.json` | Route mappings (frontend routing rules) |
| `import-config.json` | Combined import file for bulk import |

## Usage

### Prerequisites

1. MarchProxy API server running and accessible
2. Valid cluster API key from MarchProxy

### Import Configuration

```bash
# Set environment variables
export MARCHPROXY_API="http://localhost:8000"
export CLUSTER_API_KEY="your-cluster-api-key"

# Import using the provided script
./scripts/marchproxy-import.sh

# Or manually with curl
curl -X POST "$MARCHPROXY_API/api/v1/services/import" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLUSTER_API_KEY" \
    -d @config/marchproxy/import-config.json
```

### Customization

Before importing, update the following in all JSON files:

1. **Service names**: Replace `projectname` with your actual application name
2. **IP/FQDN**: Update `ip_fqdn` values to match your Docker network service names
3. **Ports**: Adjust ports if your services use different ports
4. **Auth type**: Configure `auth_type` based on your security requirements

### Service Configuration

| Service | Protocol | Port | Auth | Description |
|---------|----------|------|------|-------------|
| flask-api | HTTP | 8080 | JWT | External REST API |
| go-backend | gRPC | 50051 | None | Internal high-performance backend |
| webui | HTTP | 80 | None | Frontend web interface |

### Mapping Configuration

| Mapping | Path | Backend | Description |
|---------|------|---------|-------------|
| external-api | /api/v1/* | flask-api | REST API routing |
| webui-access | /* | webui | Frontend routing |

## Regenerating Configuration

Use the Python configuration generator:

```bash
python scripts/generate_marchproxy_config.py
```

Or regenerate from your application's settings by modifying the generator script.

## MarchProxy Documentation

For full MarchProxy documentation, see: `~/code/MarchProxy/api-server/README.md`

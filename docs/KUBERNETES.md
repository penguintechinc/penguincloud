# Kubernetes Deployment Guide

This guide covers deploying the project template to Kubernetes using three deployment approaches: Helm charts, raw manifests, and Kustomize overlays.

## Deployment Options

### Option 1: Helm Charts (Recommended)

Helm charts are located in `k8s/helm/` with pre-configured templates for each service:
- `k8s/helm/flask-backend/` - Flask backend service
- `k8s/helm/go-backend/` - Go backend service
- `k8s/helm/webui/` - WebUI frontend service

**Install a service:**
```bash
helm install my-release k8s/helm/flask-backend \
  --namespace production \
  --create-namespace \
  --values custom-values.yaml
```

**Upgrade a service:**
```bash
helm upgrade my-release k8s/helm/flask-backend \
  --namespace production \
  --values custom-values.yaml
```

**Uninstall a service:**
```bash
helm uninstall my-release --namespace production
```

### Option 2: Raw Manifests

Raw Kubernetes manifests are in `k8s/manifests/` for direct kubectl application:
- `k8s/manifests/flask-backend/` - Flask deployment files
- `k8s/manifests/go-backend/` - Go deployment files
- `k8s/manifests/webui/` - WebUI deployment files

**Apply manifests:**
```bash
kubectl apply -f k8s/manifests/flask-backend/
kubectl apply -f k8s/manifests/go-backend/
kubectl apply -f k8s/manifests/webui/
```

**View deployed resources:**
```bash
kubectl get deployments,services,ingress -n default
```

**Delete manifests:**
```bash
kubectl delete -f k8s/manifests/flask-backend/
```

### Option 3: Kustomize Overlays

Kustomize provides environment-specific overlays for dev, staging, and production:
- `k8s/kustomize/base/` - Base configurations
- `k8s/kustomize/overlays/dev/` - Development environment
- `k8s/kustomize/overlays/staging/` - Staging environment
- `k8s/kustomize/overlays/prod/` - Production environment

**Deploy to development:**
```bash
kubectl apply -k k8s/kustomize/overlays/dev/
```

**Deploy to staging:**
```bash
kubectl apply -k k8s/kustomize/overlays/staging/
```

**Deploy to production:**
```bash
kubectl apply -k k8s/kustomize/overlays/prod/
```

**Preview changes (dry-run):**
```bash
kubectl apply -k k8s/kustomize/overlays/prod/ --dry-run=client -o yaml
```

## Quick Start Commands

### Using Helm (Fastest)
```bash
# Install all services
helm install app-release k8s/helm/flask-backend -n default --create-namespace
helm install app-release k8s/helm/go-backend -n default --create-namespace
helm install app-release k8s/helm/webui -n default --create-namespace

# Check status
helm list -n default
helm status app-release -n default

# View values
helm get values app-release -n default
```

### Using kubectl + Manifests
```bash
# Apply all manifests
kubectl apply -f k8s/manifests/

# Check deployment status
kubectl get pods -n default
kubectl describe deployment -n default

# View service endpoints
kubectl get services -n default
```

### Using Kustomize
```bash
# Build and apply
kubectl apply -k k8s/kustomize/overlays/prod/

# Validate configuration
kustomize build k8s/kustomize/overlays/prod/ --enable-alpha-plugins

# Delete all resources
kubectl delete -k k8s/kustomize/overlays/prod/
```

## Environment Configuration

### For Helm
Create custom `values.yaml` files for each environment:
```yaml
# values-prod.yaml
flask-backend:
  replicaCount: 3
  resources:
    limits:
      memory: "512Mi"
      cpu: "500m"
go-backend:
  replicaCount: 2
  resources:
    limits:
      memory: "256Mi"
      cpu: "250m"
webui:
  replicaCount: 2
  resources:
    limits:
      memory: "256Mi"
      cpu: "250m"
```

### For Kustomize
Edit `k8s/kustomize/overlays/prod/kustomization.yaml` to customize resources, replicas, and environment variables for each overlay.

## Common Operations

**Scale a deployment:**
```bash
kubectl scale deployment flask-backend --replicas=5 -n production
```

**View logs:**
```bash
kubectl logs deployment/flask-backend -n production --follow
```

**Access pod shell:**
```bash
kubectl exec -it pod/flask-backend-xxx /bin/bash -n production
```

**Port forward:**
```bash
kubectl port-forward service/flask-backend 5000:5000 -n production
```

**Check resource usage:**
```bash
kubectl top nodes
kubectl top pods -n production
```

## Documentation

For more information:
- **Helm Charts**: See README in each `k8s/helm/*/` directory
- **Raw Manifests**: See README in each `k8s/manifests/*/` directory
- **Kustomize**: See `k8s/kustomize/README.md`
- **Full Deployment Guide**: See [docs/deployment/](../deployment/)

## Support

For troubleshooting and advanced configurations, refer to the complete deployment documentation in the `docs/` folder.

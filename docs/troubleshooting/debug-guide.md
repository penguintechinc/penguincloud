# Troubleshooting & Debug Guide

This guide provides practical troubleshooting steps for common issues in the project-template environment.

## Table of Contents

1. [Common Issues](#common-issues)
2. [Debug Commands](#debug-commands)
3. [Environment Troubleshooting](#environment-troubleshooting)
4. [Network Troubleshooting](#network-troubleshooting)
5. [Performance Troubleshooting](#performance-troubleshooting)
6. [Log Analysis](#log-analysis)
7. [Support Resources](#support-resources)

---

## Common Issues

### 1. Port Conflicts

**Symptoms**: Services fail to start, "port already in use" error messages

**Quick Diagnosis**:
```bash
lsof -i :5000          # Flask backend
lsof -i :3000          # WebUI frontend
lsof -i :8080          # Go backend
lsof -i :5432          # PostgreSQL
netstat -tlnp
```

**Solutions**:
- Edit `docker-compose.yml` and remap ports
- Kill existing process: `kill -9 <PID>`
- Use different docker-compose file: `docker-compose -f docker-compose.dev.yml up`

### 2. Database Connection Issues

**Symptoms**: "Connection refused", "password authentication failed", connection timeouts

**Quick Diagnosis**:
```bash
docker-compose exec postgres psql -U postgres -d template1 -c "SELECT 1"
docker-compose exec flask-backend env | grep DB_
```

**Common Causes & Solutions**:

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" | Database not running | Run `make dev` or `docker-compose up` |
| "password authentication failed" | Wrong credentials | Verify DB_USER, DB_PASS in `.env` |
| Connection timeout | Wrong host/port | Check DB_HOST and DB_PORT |
| Galera WSREP_NOT_READY | Galera node not ready | Wait 30 seconds, check logs |

**Verification Steps**:
```bash
docker-compose ps postgres
docker-compose exec flask-backend env | grep "^DB_"
docker-compose logs postgres
```

### 3. License Validation Failures

**Symptoms**: "License validation failed", feature access denied

**Quick Diagnosis**:
```bash
docker-compose exec flask-backend env | grep -i license
curl -v https://license.penguintech.io/api/v2/validate
```

**Common Causes & Solutions**:

| Issue | Cause | Solution |
|-------|-------|----------|
| "Invalid license format" | Malformed key | Verify format: `PENG-XXXX-XXXX-XXXX-XXXX-ABCD` |
| "License expired" | License date passed | Renew through PenguinTech portal |
| "License server unreachable" | Network issue | Check internet, verify LICENSE_SERVER_URL |
| "Development mode" | RELEASE_MODE not set | License checks only in production |

**Verification Steps**:
```bash
make license-validate
make license-check-features
make license-debug
```

### 4. Build Failures

**Symptoms**: Docker build errors, dependency failures, compilation errors

**Quick Diagnosis**:
```bash
docker --version
docker buildx version
docker-compose build --no-cache flask-backend
```

**Python/Flask**:
```bash
docker-compose exec flask-backend pip list
docker-compose exec flask-backend pip cache purge
make clean && make build
```

**Node.js/WebUI**:
```bash
docker-compose exec webui node --version
docker-compose exec webui npm cache clean --force
make clean && make build
```

**Go**:
```bash
docker-compose exec go-backend go version
docker-compose exec go-backend go mod verify
docker-compose exec go-backend go build -v ./...
```

### 5. Test Failures

**Symptoms**: Tests fail locally, pass in CI/CD, inconsistent results

**Quick Diagnosis**:
```bash
make test-unit -- -v
make test-integration -- -v
docker-compose logs | grep -i test
```

**Common Causes & Solutions**:

| Issue | Cause | Solution |
|-------|-------|----------|
| Pass locally, fail in CI | Environment differences | Check CI environment in `.github/workflows/` |
| Database tests fail | Test DB not initialized | Run `make setup` first |
| Flaky tests | Timing issues | Add retry logic, increase timeouts |
| Port binding failures | Port in use | Use dynamic ports in tests |

---

## Debug Commands

### Container Debugging

```bash
docker-compose logs flask-backend
docker-compose logs -f go-backend          # Follow logs
docker-compose logs --tail=100 webui       # Last 100 lines
docker-compose logs -f --timestamps flask-backend

docker-compose logs flask-backend | grep -i error
docker-compose logs flask-backend | grep -i warning

docker-compose exec flask-backend /bin/bash
docker-compose exec postgres psql -U postgres

docker-compose exec flask-backend ls -la /app
```

### Application Debugging

```bash
make debug                                  # Start with debug flags
make logs                                   # View application logs
make health                                 # Check service health

curl http://localhost:5000/healthz          # Flask
curl http://localhost:3000/health           # WebUI
curl http://localhost:8080/healthz          # Go
```

### License Debugging

```bash
make license-debug
make license-validate
make license-check-features
docker-compose logs flask-backend | grep -i license
```

---

## Environment Troubleshooting

### Configuration Issues

```bash
docker-compose exec flask-backend env | sort
docker-compose exec flask-backend env | grep DB_
docker-compose exec flask-backend env | grep SECRET_
ls -la .env
```

**Load order**:
1. `.env` file loaded first
2. `docker-compose.yml` environment overrides `.env`
3. Container environment takes precedence

### Python Environment Issues

```bash
docker-compose exec flask-backend python3 --version
docker-compose exec flask-backend which python3
docker-compose exec flask-backend pip list
docker-compose exec flask-backend pip check
```

### Node.js Environment Issues

```bash
docker-compose exec webui node --version
docker-compose exec webui npm --version
docker-compose exec webui ls node_modules | head -20
docker-compose exec webui ls -la build/
```

---

## Network Troubleshooting

### Container Communication

```bash
docker-compose exec flask-backend curl http://webui:3000
docker-compose exec flask-backend curl http://go-backend:8080
docker-compose exec webui curl http://flask-backend:5000/api/v1/health

docker-compose exec flask-backend ping webui
docker-compose exec flask-backend getent hosts postgres

docker network inspect project-template_default
docker network ls
```

### DNS Resolution

```bash
docker-compose exec flask-backend nslookup postgres
docker-compose exec flask-backend getent hosts webui
docker-compose exec flask-backend cat /etc/hosts
```

### Port Binding Issues

```bash
docker-compose port flask-backend 5000
docker-compose port webui 3000
netstat -tlnp | grep LISTEN
ss -tlnp | grep LISTEN
```

---

## Performance Troubleshooting

### High CPU Usage

```bash
docker stats flask-backend
docker stats go-backend
docker-compose exec flask-backend python3 -m cProfile app.py
docker-compose exec flask-backend top -n 1
```

### Memory Issues

```bash
docker inspect project-template_flask-backend-1 | grep Memory
docker stats flask-backend --no-stream=false
docker-compose exec flask-backend ps aux --sort=-%mem
```

### Slow Queries

```bash
docker-compose exec postgres psql -U postgres -c \
  "ALTER SYSTEM SET log_min_duration_statement = 1000;"
docker-compose logs postgres | grep slow
docker-compose exec postgres psql -U postgres -d your_db \
  -c "EXPLAIN ANALYZE SELECT * FROM users LIMIT 10;"
```

### Bottleneck Analysis

```bash
docker stats --no-stream flask-backend go-backend
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:5000/api/v1/users
```

---

## Log Analysis

### Finding Errors and Warnings

```bash
docker-compose logs | grep -i error
docker-compose logs | grep -B2 -A2 "error"
docker-compose logs flask-backend | grep ERROR
docker-compose logs go-backend | grep WARN
docker-compose logs | grep -i error | wc -l
```

### Analyzing Specific Issues

```bash
# Authentication errors
docker-compose logs | grep -i "auth\|permission\|unauthorized"

# Database errors
docker-compose logs | grep -i "connection\|query\|database"

# License errors
docker-compose logs | grep -i "license\|validation"

# Network errors
docker-compose logs | grep -i "timeout\|refused\|unreachable"
```

### Saving Logs for Analysis

```bash
docker-compose logs > /tmp/project-logs.txt
docker-compose logs --timestamps > /tmp/project-logs-ts.txt
```

---

## Support Resources

### Documentation

- **Technical Documentation**: [Development Standards](../STANDARDS.md)
- **License Integration**: [License Server Guide](../licensing/license-server-integration.md)
- **Kubernetes Deployment**: [Kubernetes Guide](../KUBERNETES.md)
- **Workflow Documentation**: [CI/CD Workflows](../WORKFLOWS.md)

### Getting Help

- **Technical Support**: support@penguintech.io
- **Sales Inquiries**: sales@penguintech.io
- **License Issues**: licenses@penguintech.io

### System Status

- **License Server Status**: https://status.penguintech.io
- **PenguinTech Status Page**: https://www.penguintech.io/status

---

## Quick Reference Checklist

When troubleshooting, verify:

- [ ] Service is running: `docker-compose ps`
- [ ] Correct ports mapped: `docker-compose port <service>`
- [ ] Environment variables set: `docker-compose exec <service> env`
- [ ] Database accessible: Test connection from app container
- [ ] Network connectivity: Ping between containers
- [ ] Logs show no errors: `docker-compose logs <service>`
- [ ] Recent changes reviewed: `git diff`
- [ ] Clean rebuild attempted: `make clean && make build`
- [ ] All containers healthy: `make health`

---

**Last Updated**: December 2025
**Version**: 1.0.0

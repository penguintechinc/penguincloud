# Project Template Makefile
# This Makefile provides common development tasks for multi-language projects

.PHONY: help setup dev test build clean lint format docker deploy

# Default target
.DEFAULT_GOAL := help

# Variables
PROJECT_NAME := project-template
VERSION := $(shell cat .version 2>/dev/null || echo "development")
DOCKER_REGISTRY := ghcr.io
DOCKER_ORG := penguintechinc
GO_VERSION := 1.24.2
PYTHON_VERSION := 3.12
NODE_VERSION := 18
FLUTTER_VERSION := 3.38.9

# Colors for output
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

# Help target
help: ## Show this help message
	@echo "$(BLUE)$(PROJECT_NAME) Development Commands$(RESET)"
	@echo ""
	@echo "$(GREEN)Setup Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Setup/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Development Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Development/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Testing Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Testing/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Build Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Build/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Docker Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Docker/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Other Commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && !/Setup|Development|Testing|Build|Docker/ {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Setup Commands
setup: ## Setup - Install all dependencies and initialize the project
	@echo "$(BLUE)Setting up $(PROJECT_NAME)...$(RESET)"
	@$(MAKE) setup-env
	@$(MAKE) setup-go
	@$(MAKE) setup-python
	@$(MAKE) setup-node
	@$(MAKE) setup-flutter
	@$(MAKE) setup-git-hooks
	@echo "$(GREEN)Setup complete!$(RESET)"

setup-env: ## Setup - Create environment file from template
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from .env.example...$(RESET)"; \
		cp .env.example .env; \
		echo "$(YELLOW)Please edit .env with your configuration$(RESET)"; \
	fi

setup-go: ## Setup - Install Go dependencies and tools
	@echo "$(BLUE)Setting up Go dependencies...$(RESET)"
	@go version || (echo "$(RED)Go $(GO_VERSION) not installed$(RESET)" && exit 1)
	@go mod download
	@go mod tidy
	@go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	@go install github.com/air-verse/air@latest

setup-python: ## Setup - Install Python dependencies and tools
	@echo "$(BLUE)Setting up Python dependencies...$(RESET)"
	@python3 --version || (echo "$(RED)Python $(PYTHON_VERSION) not installed$(RESET)" && exit 1)
	@pip install --upgrade pip
	@pip install -r requirements.txt
	@pip install black isort flake8 mypy pytest pytest-cov

setup-node: ## Setup - Install Node.js dependencies and tools
	@echo "$(BLUE)Setting up Node.js dependencies...$(RESET)"
	@node --version || (echo "$(RED)Node.js $(NODE_VERSION) not installed$(RESET)" && exit 1)
	@npm install
	@cd web && npm install

setup-git-hooks: ## Setup - Install Git pre-commit hooks
	@echo "$(BLUE)Installing Git hooks...$(RESET)"
	@cp scripts/git-hooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@cp scripts/git-hooks/commit-msg .git/hooks/commit-msg
	@chmod +x .git/hooks/commit-msg

setup-flutter: ## Setup - Install Flutter dependencies
	@echo "$(BLUE)Setting up Flutter dependencies...$(RESET)"
	@flutter --version || (echo "$(RED)Flutter not installed$(RESET)" && exit 1)
	@cd services/mobile && flutter pub get

# Development Commands
dev: ## Development - Start development environment
	@echo "$(BLUE)Starting development environment...$(RESET)"
	@docker-compose up -d postgres redis
	@sleep 5
	@$(MAKE) dev-services

dev-services: ## Development - Start all services for development
	@echo "$(BLUE)Starting development services...$(RESET)"
	@trap 'docker-compose down' INT; \
	concurrently --names "API,Web-Python,Web-Node" --prefix name --kill-others \
		"$(MAKE) dev-api" \
		"$(MAKE) dev-web-python" \
		"$(MAKE) dev-web-node"

dev-api: ## Development - Start Go API in development mode
	@echo "$(BLUE)Starting Go API...$(RESET)"
	@cd apps/api && air

dev-web-python: ## Development - Start Python web app in development mode
	@echo "$(BLUE)Starting Python web app...$(RESET)"
	@cd apps/web && python app.py

dev-web-node: ## Development - Start Node.js web app in development mode
	@echo "$(BLUE)Starting Node.js web app...$(RESET)"
	@cd web && npm run dev

dev-db: ## Development - Start only database services
	@docker-compose up -d postgres redis

dev-monitoring: ## Development - Start monitoring services
	@docker-compose up -d prometheus grafana

dev-mobile: ## Development - Launch Flutter mobile app in development mode
	@echo "$(BLUE)Starting Flutter mobile app...$(RESET)"
	@cd services/mobile && flutter run

dev-full: ## Development - Start full development stack
	@docker-compose up -d

# Testing Commands
test: ## Testing - Run all tests
	@echo "$(BLUE)Running all tests...$(RESET)"
	@$(MAKE) test-go
	@$(MAKE) test-python
	@$(MAKE) test-node
	@$(MAKE) test-flutter
	@$(MAKE) smoke-test
	@echo "$(GREEN)All tests completed!$(RESET)"

test-go: ## Testing - Run Go tests
	@echo "$(BLUE)Running Go tests...$(RESET)"
	@go test -v -race -coverprofile=coverage-go.out ./...

test-python: ## Testing - Run Python tests
	@echo "$(BLUE)Running Python tests...$(RESET)"
	@pytest --cov=shared --cov=apps --cov-report=xml:coverage-python.xml --cov-report=html:htmlcov-python

test-node: ## Testing - Run Node.js tests
	@echo "$(BLUE)Running Node.js tests...$(RESET)"
	@npm test
	@cd web && npm test

test-flutter: ## Testing - Run Flutter tests
	@echo "$(BLUE)Running Flutter tests...$(RESET)"
	@cd services/mobile && flutter test

smoke-test: ## Testing - Run all smoke tests (build + runtime)
	@echo "$(BLUE)Running smoke tests...$(RESET)"
	@./tests/smoke/run-all.sh

smoke-test-build: ## Testing - Run build smoke tests only
	@echo "$(BLUE)Running build smoke tests...$(RESET)"
	@for test in tests/smoke/build/*.sh; do \
		[ -f "$$test" ] && $$test || exit 1; \
	done

smoke-test-mobile: ## Testing - Run mobile smoke tests
	@echo "$(BLUE)Running mobile smoke tests...$(RESET)"
	@./tests/smoke/build/test-mobile-android.sh

test-integration: ## Testing - Run integration tests
	@echo "$(BLUE)Running integration tests...$(RESET)"
	@docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
	@docker-compose -f docker-compose.test.yml down

test-coverage: ## Testing - Generate coverage reports
	@$(MAKE) test
	@echo "$(GREEN)Coverage reports generated:$(RESET)"
	@echo "  Go: coverage-go.out"
	@echo "  Python: coverage-python.xml, htmlcov-python/"
	@echo "  Node.js: coverage/"

# Build Commands
build: ## Build - Build all applications
	@echo "$(BLUE)Building all applications...$(RESET)"
	@$(MAKE) build-go
	@$(MAKE) build-python
	@$(MAKE) build-node
	@$(MAKE) build-flutter
	@echo "$(GREEN)All builds completed!$(RESET)"

build-go: ## Build - Build Go applications
	@echo "$(BLUE)Building Go applications...$(RESET)"
	@mkdir -p bin
	@go build -ldflags "-X main.version=$(VERSION)" -o bin/api ./apps/api

build-python: ## Build - Build Python applications
	@echo "$(BLUE)Building Python applications...$(RESET)"
	@python -m py_compile apps/web/app.py

build-node: ## Build - Build Node.js applications
	@echo "$(BLUE)Building Node.js applications...$(RESET)"
	@npm run build
	@cd web && npm run build

build-flutter: ## Build - Build Flutter APK
	@echo "$(BLUE)Building Flutter APK...$(RESET)"
	@cd services/mobile && flutter build apk --release

build-production: ## Build - Build for production with optimizations
	@echo "$(BLUE)Building for production...$(RESET)"
	@CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -ldflags "-w -s -X main.version=$(VERSION)" -o bin/api ./apps/api
	@cd web && npm run build

# Docker Commands
docker-build: ## Docker - Build all Docker images
	@echo "$(BLUE)Building Docker images...$(RESET)"
	@docker build -t $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-api:$(VERSION) -f apps/api/Dockerfile .
	@docker build -t $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-web:$(VERSION) -f web/Dockerfile web/
	@docker build -t $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-python:$(VERSION) -f apps/web/Dockerfile .

docker-push: ## Docker - Push Docker images to registry
	@echo "$(BLUE)Pushing Docker images...$(RESET)"
	@docker push $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-api:$(VERSION)
	@docker push $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-web:$(VERSION)
	@docker push $(DOCKER_REGISTRY)/$(DOCKER_ORG)/$(PROJECT_NAME)-python:$(VERSION)

docker-run: ## Docker - Run application with Docker Compose
	@docker-compose up --build

docker-clean: ## Docker - Clean up Docker resources
	@echo "$(BLUE)Cleaning up Docker resources...$(RESET)"
	@docker-compose down -v
	@docker system prune -f

# Code Quality Commands
lint: ## Code Quality - Run linting for all languages
	@echo "$(BLUE)Running linting...$(RESET)"
	@$(MAKE) lint-go
	@$(MAKE) lint-python
	@$(MAKE) lint-node
	@$(MAKE) lint-flutter

lint-go: ## Code Quality - Run Go linting
	@echo "$(BLUE)Linting Go code...$(RESET)"
	@golangci-lint run

lint-python: ## Code Quality - Run Python linting
	@echo "$(BLUE)Linting Python code...$(RESET)"
	@flake8 .
	@mypy . --ignore-missing-imports

lint-node: ## Code Quality - Run Node.js linting
	@echo "$(BLUE)Linting Node.js code...$(RESET)"
	@npm run lint
	@cd web && npm run lint

lint-flutter: ## Code Quality - Run Flutter analysis
	@echo "$(BLUE)Analyzing Flutter code...$(RESET)"
	@cd services/mobile && flutter analyze

format: ## Code Quality - Format code for all languages
	@echo "$(BLUE)Formatting code...$(RESET)"
	@$(MAKE) format-go
	@$(MAKE) format-python
	@$(MAKE) format-node
	@$(MAKE) format-flutter

format-go: ## Code Quality - Format Go code
	@echo "$(BLUE)Formatting Go code...$(RESET)"
	@go fmt ./...
	@goimports -w .

format-python: ## Code Quality - Format Python code
	@echo "$(BLUE)Formatting Python code...$(RESET)"
	@black .
	@isort .

format-node: ## Code Quality - Format Node.js code
	@echo "$(BLUE)Formatting Node.js code...$(RESET)"
	@npm run format
	@cd web && npm run format

format-flutter: ## Code Quality - Format Flutter/Dart code
	@echo "$(BLUE)Formatting Dart code...$(RESET)"
	@cd services/mobile && dart format .

# Database Commands
db-migrate: ## Database - Run database migrations
	@echo "$(BLUE)Running database migrations...$(RESET)"
	@go run scripts/migrate.go

db-seed: ## Database - Seed database with test data
	@echo "$(BLUE)Seeding database...$(RESET)"
	@go run scripts/seed.go

db-reset: ## Database - Reset database (WARNING: destroys data)
	@echo "$(RED)WARNING: This will destroy all data!$(RESET)"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ]
	@docker-compose down -v
	@docker-compose up -d postgres redis
	@sleep 5
	@$(MAKE) db-migrate
	@$(MAKE) db-seed

db-backup: ## Database - Create database backup
	@echo "$(BLUE)Creating database backup...$(RESET)"
	@mkdir -p backups
	@docker-compose exec postgres pg_dump -U postgres project_template > backups/backup-$(shell date +%Y%m%d-%H%M%S).sql

db-restore: ## Database - Restore database from backup (requires BACKUP_FILE)
	@echo "$(BLUE)Restoring database from $(BACKUP_FILE)...$(RESET)"
	@docker-compose exec -T postgres psql -U postgres project_template < $(BACKUP_FILE)

# License Commands
license-validate: ## License - Validate license configuration
	@echo "$(BLUE)Validating license configuration...$(RESET)"
	@go run scripts/license-validate.go

license-test: ## License - Test license server integration
	@echo "$(BLUE)Testing license server integration...$(RESET)"
	@curl -f $${LICENSE_SERVER_URL:-https://license.penguintech.io}/api/v2/validate \
		-H "Authorization: Bearer $${LICENSE_KEY}" \
		-H "Content-Type: application/json" \
		-d '{"product": "'$${PRODUCT_NAME:-project-template}'"}'

# Version Management Commands
version-update: ## Version - Update version (patch by default)
	@./scripts/version/update-version.sh

version-update-minor: ## Version - Update minor version
	@./scripts/version/update-version.sh minor

version-update-major: ## Version - Update major version
	@./scripts/version/update-version.sh major

version-show: ## Version - Show current version
	@echo "Current version: $(VERSION)"

# Deployment Commands
deploy-staging: ## Deploy - Deploy to staging environment
	@echo "$(BLUE)Deploying to staging...$(RESET)"
	@$(MAKE) docker-build
	@$(MAKE) docker-push
	# Add staging deployment commands here

deploy-production: ## Deploy - Deploy to production environment
	@echo "$(BLUE)Deploying to production...$(RESET)"
	@$(MAKE) docker-build
	@$(MAKE) docker-push
	# Add production deployment commands here

# Health Check Commands
health: ## Health - Check service health
	@echo "$(BLUE)Checking service health...$(RESET)"
	@curl -f http://localhost:8080/health || echo "$(RED)API health check failed$(RESET)"
	@curl -f http://localhost:8000/health || echo "$(RED)Python web health check failed$(RESET)"
	@curl -f http://localhost:3000/health || echo "$(RED)Node web health check failed$(RESET)"

logs: ## Logs - Show service logs
	@docker-compose logs -f

logs-api: ## Logs - Show API logs
	@docker-compose logs -f api

logs-web: ## Logs - Show web logs
	@docker-compose logs -f web-python web-node

logs-db: ## Logs - Show database logs
	@docker-compose logs -f postgres redis

# Cleanup Commands
clean: ## Clean - Clean build artifacts and caches
	@echo "$(BLUE)Cleaning build artifacts...$(RESET)"
	@rm -rf bin/
	@rm -rf dist/
	@rm -rf node_modules/
	@rm -rf web/node_modules/
	@rm -rf web/dist/
	@rm -rf services/mobile/build/
	@rm -rf services/mobile/.dart_tool/
	@rm -rf __pycache__/
	@rm -rf .pytest_cache/
	@rm -rf htmlcov-python/
	@rm -rf coverage-*.out
	@rm -rf coverage-*.xml
	@go clean -cache -modcache

clean-docker: ## Clean - Clean Docker resources
	@$(MAKE) docker-clean

clean-all: ## Clean - Clean everything (build artifacts, Docker, etc.)
	@$(MAKE) clean
	@$(MAKE) clean-docker

# Security Commands
security-scan: ## Security - Run security scans
	@echo "$(BLUE)Running security scans...$(RESET)"
	@go list -json -m all | nancy sleuth
	@safety check --json

audit: ## Security - Run security audit
	@echo "$(BLUE)Running security audit...$(RESET)"
	@npm audit
	@cd web && npm audit
	@$(MAKE) security-scan

# Monitoring Commands
metrics: ## Monitoring - Show application metrics
	@echo "$(BLUE)Application metrics:$(RESET)"
	@curl -s http://localhost:8080/metrics | grep -E '^# (HELP|TYPE)' | head -20

monitor: ## Monitoring - Open monitoring dashboard
	@echo "$(BLUE)Opening monitoring dashboard...$(RESET)"
	@open http://localhost:3001  # Grafana

# Documentation Commands
docs-serve: ## Documentation - Serve documentation locally
	@echo "$(BLUE)Serving documentation...$(RESET)"
	@cd docs && python -m http.server 8080

docs-build: ## Documentation - Build documentation
	@echo "$(BLUE)Building documentation...$(RESET)"
	@echo "Documentation build not implemented yet"

# Git Commands
git-hooks-install: ## Git - Install Git hooks
	@$(MAKE) setup-git-hooks

git-hooks-test: ## Git - Test Git hooks
	@echo "$(BLUE)Testing Git hooks...$(RESET)"
	@.git/hooks/pre-commit
	@echo "$(GREEN)Git hooks test completed$(RESET)"

# Info Commands
info: ## Info - Show project information
	@echo "$(BLUE)Project Information:$(RESET)"
	@echo "Name: $(PROJECT_NAME)"
	@echo "Version: $(VERSION)"
	@echo "Go Version: $(GO_VERSION)"
	@echo "Python Version: $(PYTHON_VERSION)"
	@echo "Node Version: $(NODE_VERSION)"
	@echo ""
	@echo "$(BLUE)Service URLs:$(RESET)"
	@echo "API: http://localhost:8080"
	@echo "Python Web: http://localhost:8000"
	@echo "Node Web: http://localhost:3000"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3001"

proto-compile: ## Build - Compile proto files to Go and Python
	@echo "$(BLUE)Compiling proto files...$(RESET)"
	@# Compile Flask backend protos
	@python -m grpc_tools.protoc -I./services/flask-backend/app/grpc/protos \
		--python_out=./services/flask-backend/app/grpc \
		--grpc_python_out=./services/flask-backend/app/grpc \
		./services/flask-backend/app/grpc/protos/template.proto || echo "Note: Python proto tools may need installation"
	@# Compile Go backend protos
	@protoc -I./services/go-backend/internal/grpc/protos \
		--go_out=./services/go-backend/internal/grpc/protos \
		--go-grpc_out=./services/go-backend/internal/grpc/protos \
		./services/go-backend/internal/grpc/protos/template.proto || echo "Note: protoc may need installation"
	@echo "$(GREEN)Proto compilation complete$(RESET)"

env: ## Info - Show environment variables
	@echo "$(BLUE)Environment Variables:$(RESET)"
	@env | grep -E "^(LICENSE_|POSTGRES_|REDIS_|NODE_|GIN_|PY4WEB_)" | sort

# === Kubernetes Deployment (microk8s + Helm v3) ===
PROJECT_NAME := $(shell basename $(CURDIR))
HELM_DIR := k8s/helm/$(PROJECT_NAME)

k8s-alpha-deploy: ## K8s - Build, deploy, and test on microk8s (alpha)
	@./tests/k8s/alpha/run-all-alpha.sh

k8s-beta-deploy: ## K8s - Deploy to beta cluster with beta values
	@./tests/k8s/beta/run-all-beta.sh

k8s-prod-deploy: ## K8s - Deploy to production (requires confirmation)
	@read -p "Deploy to PRODUCTION? (yes/NO): " c && [ "$$c" = "yes" ]
	@helm upgrade --install $(PROJECT_NAME) ./$(HELM_DIR) \
		--namespace $(PROJECT_NAME)-prod --create-namespace \
		--values ./$(HELM_DIR)/values.yaml --wait --timeout 10m

k8s-alpha-test: ## K8s - Run alpha smoke tests only
	@./tests/k8s/alpha/run-all-alpha.sh

k8s-beta-test: ## K8s - Run beta smoke tests only
	@./tests/k8s/beta/run-all-beta.sh

k8s-cleanup: ## K8s - Clean up all K8s namespaces for this project
	@helm uninstall $(PROJECT_NAME) -n $(PROJECT_NAME)-alpha 2>/dev/null || true
	@helm uninstall $(PROJECT_NAME) -n $(PROJECT_NAME)-beta 2>/dev/null || true
	@microk8s kubectl delete namespace $(PROJECT_NAME)-alpha 2>/dev/null || true
	@microk8s kubectl delete namespace $(PROJECT_NAME)-beta 2>/dev/null || true

helm-lint: ## Helm - Lint chart
	@helm lint ./$(HELM_DIR)

helm-template: ## Helm - Render templates (dry-run)
	@helm template $(PROJECT_NAME) ./$(HELM_DIR) --values ./$(HELM_DIR)/values-alpha.yaml
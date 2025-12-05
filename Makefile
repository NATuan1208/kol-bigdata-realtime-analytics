SHELL := /bin/bash

# ============================================================================
# KOL Big Data Analytics Platform — Makefile
# ============================================================================
# This Makefile provides convenient commands for managing the KOL infrastructure.
#
# IMPORTANT: This project REUSES infrastructure from SME Pulse project:
#   - MinIO (sme-minio)
#   - PostgreSQL (sme-postgres)  
#   - Trino (sme-trino)
#   - Hive Metastore (sme-hive-metastore)
#   - Airflow (sme-airflow-webserver)
#
# Prerequisites:
#   1. SME Pulse project must be running first
#   2. Shared network 'sme-network' must exist: make network-create
#   3. SME Pulse services must be on 'sme-network'
# ============================================================================

.DEFAULT_GOAL := help

# Environment files
ENV_KOL := .env.kol

# Docker Compose files
COMPOSE_KOL := infra/docker-compose.kol.yml

# Project name
PROJECT_NAME := kol-platform

# Shared network name (must match SME Pulse)
SHARED_NETWORK := sme_pulse_sme-network

# ============================================================================
# HELP
# ============================================================================
.PHONY: help
help: ## Show this help message
	@echo "KOL Big Data Analytics Platform — Available Commands"
	@echo "===================================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# NETWORK SETUP
# ============================================================================
.PHONY: network-create
network-create: ## Create shared Docker network (sme-network)
	@echo "Creating shared network: $(SHARED_NETWORK)..."
	@docker network create $(SHARED_NETWORK) 2>/dev/null || echo "Network already exists"

.PHONY: network-remove
network-remove: ## Remove shared Docker network
	@echo "WARNING: This will remove the shared network used by both SME Pulse and KOL"
	@echo "Make sure both projects are stopped before removing the network"
	@read -p "Continue? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker network rm $(SHARED_NETWORK) 2>/dev/null || echo "Network doesn't exist"

.PHONY: network-inspect
network-inspect: ## Inspect shared network and connected containers
	@echo "Inspecting shared network: $(SHARED_NETWORK)..."
	@docker network inspect $(SHARED_NETWORK) 2>/dev/null || echo "Network doesn't exist. Run 'make network-create' first"

# ============================================================================
# SME PULSE VERIFICATION (Prerequisites)
# ============================================================================
.PHONY: check-sme
check-sme: ## Verify SME Pulse services are running
	@echo "Checking SME Pulse prerequisites..."
	@echo -n "  - Network $(SHARED_NETWORK): "
	@docker network inspect $(SHARED_NETWORK) >/dev/null 2>&1 && echo "✓ OK" || (echo "✗ MISSING" && exit 1)
	@echo -n "  - sme-postgres: "
	@docker ps --filter "name=sme-postgres" --filter "status=running" | grep -q sme-postgres && echo "✓ Running" || (echo "✗ Not running" && exit 1)
	@echo -n "  - sme-minio: "
	@docker ps --filter "name=sme-minio" --filter "status=running" | grep -q sme-minio && echo "✓ Running" || (echo "✗ Not running" && exit 1)
	@echo -n "  - sme-trino: "
	@docker ps --filter "name=sme-trino" --filter "status=running" | grep -q sme-trino && echo "✓ Running" || (echo "✗ Not running" && exit 1)
	@echo -n "  - sme-hive-metastore: "
	@docker ps --filter "name=sme-hive-metastore" --filter "status=running" | grep -q sme-hive-metastore && echo "✓ Running" || (echo "✗ Not running" && exit 1)
	@echo ""
	@echo "All SME Pulse prerequisites are satisfied ✓"

# ============================================================================
# KOL NAMESPACE INITIALIZATION
# ============================================================================
.PHONY: init-kol-namespace
init-kol-namespace: check-sme ## Initialize KOL domain namespaces (buckets, DBs, schemas)
	@echo "Initializing KOL Analytics domain namespaces..."
	@echo "This will create:"
	@echo "  - MinIO buckets: kol-bronze, kol-silver, kol-gold, kol-mlflow"
	@echo "  - PostgreSQL databases: kol_mlflow, kol_metadata"
	@echo "  - Trino schemas: iceberg.kol_bronze, kol_silver, kol_gold"
	@echo "  - Cassandra keyspace: kol_metrics"
	@echo ""
	@bash infra/scripts/init-kol-namespace.sh

.PHONY: validate-separation
validate-separation: ## Validate KOL/SME domain separation (buckets, DBs, schemas)
	@bash infra/scripts/validate-domain-separation.sh

# ============================================================================
# KOL STACK
# ============================================================================
.PHONY: up-kol
up-kol: check-sme ## Start KOL stack (requires SME Pulse running)
	@echo "Starting KOL stack..."
	@docker compose -f $(COMPOSE_KOL) --env-file $(ENV_KOL) up -d
	@echo ""
	@echo "KOL stack is starting. Access points:"
	@echo "  - Redpanda Console: http://localhost:8082"
	@echo "  - Spark Master UI: http://localhost:8084"
	@echo "  - MLflow UI: http://localhost:5000"
	@echo "  - Inference API: http://localhost:8080"
	@echo "  - Jupyter: http://localhost:8888"
	@echo ""
	@echo "Shared SME Pulse services:"
	@echo "  - MinIO Console: http://localhost:9001"
	@echo "  - Trino: http://localhost:8080"
	@echo "  - Airflow: http://localhost:8081"

.PHONY: up-kol-force
up-kol-force: ## Start KOL stack without checking SME Pulse (use with caution)
	@echo "WARNING: Starting KOL stack without verifying SME Pulse..."
	@docker compose -f $(COMPOSE_KOL) --env-file $(ENV_KOL) up -d

.PHONY: down-kol
down-kol: ## Stop KOL stack (SME Pulse services remain running)
	@echo "Stopping KOL stack..."
	@docker compose -f $(COMPOSE_KOL) down
	@echo "KOL stack stopped. SME Pulse services remain running."

.PHONY: restart-kol
restart-kol: down-kol up-kol ## Restart KOL stack

.PHONY: logs-kol
logs-kol: ## Show KOL stack logs
	@docker compose -f $(COMPOSE_KOL) logs -f

.PHONY: logs-api
logs-api: ## Show API logs
	@docker compose -f $(COMPOSE_KOL) logs -f api

.PHONY: logs-trainer
logs-trainer: ## Show trainer logs
	@docker compose -f $(COMPOSE_KOL) logs -f trainer

.PHONY: logs-spark
logs-spark: ## Show Spark logs
	@docker compose -f $(COMPOSE_KOL) logs -f spark-master

.PHONY: logs-redpanda
logs-redpanda: ## Show Redpanda logs
	@docker compose -f $(COMPOSE_KOL) logs -f redpanda

.PHONY: ps-kol
ps-kol: ## Show KOL stack status
	@docker compose -f $(COMPOSE_KOL) ps

# ============================================================================
# DEVELOPMENT
# ============================================================================
.PHONY: dev-up
dev-up: up-kol ## Alias for up-kol (start full stack)

.PHONY: dev-down
dev-down: down-all ## Alias for down-all (stop everything)

.PHONY: build
build: ## Build custom Docker images
	@echo "Building custom images..."
	@docker compose -f $(COMPOSE_KOL) build

.PHONY: rebuild
rebuild: ## Rebuild and restart KOL services
	@echo "Rebuilding KOL services..."
	@docker compose -f $(COMPOSE_KOL) up -d --build

# ============================================================================
# UTILITY COMMANDS
# ============================================================================
.PHONY: clean
clean: down-all ## Clean up containers and volumes
	@echo "Cleaning up Docker resources..."
	@docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_KOL) down -v
	@docker system prune -f

.PHONY: clean-all
clean-all: clean ## Deep clean (including images)
	@echo "Deep cleaning (including images)..."
	@docker system prune -af

.PHONY: exec-api
exec-api: ## Open shell in API container
	@docker exec -it kol-api /bin/bash

.PHONY: exec-trainer
exec-trainer: ## Open shell in trainer container
	@docker exec -it kol-trainer /bin/bash

.PHONY: exec-postgres
exec-postgres: ## Open PostgreSQL shell
	@docker exec -it base-postgres psql -U admin -d metastore

.PHONY: exec-redis
exec-redis: ## Open Redis CLI
	@docker exec -it kol-redis redis-cli

.PHONY: exec-cassandra
exec-cassandra: ## Open Cassandra CQL shell
	@docker exec -it kol-cassandra cqlsh

# ============================================================================
# INITIALIZATION & SETUP
# ============================================================================
.PHONY: init
init: network-create ## Initialize environment files and directories
	@echo "Initializing KOL platform..."
	@test -f $(ENV_BASE) || cp $(ENV_BASE) .env.base.local
	@test -f $(ENV_KOL) || cp $(ENV_KOL) .env.kol.local
	@mkdir -p data notebooks logs
	@echo "Initialization complete. Edit .env.base.local and .env.kol.local as needed."

.PHONY: init-buckets
init-buckets: ## Initialize MinIO buckets (run after base platform is up)
	@echo "Initializing MinIO buckets..."
	@docker compose -f $(COMPOSE_BASE) up -d minio-init

.PHONY: init-topics
init-topics: ## Initialize Kafka topics (run after KOL stack is up)
	@echo "Initializing Kafka topics..."
	@docker compose -f $(COMPOSE_KOL) up -d redpanda-init

.PHONY: init-db
init-db: ## Initialize database schemas
	@echo "Initializing database schemas..."
	@docker exec -i base-postgres psql -U admin -d metastore < infra/scripts/init-schemas.sql

# ============================================================================
# TESTING
# ============================================================================
.PHONY: test
test: ## Run all tests
	@echo "Running tests..."
	@pytest tests/ -v

.PHONY: test-unit
test-unit: ## Run unit tests only
	@pytest tests/unit/ -v

.PHONY: test-e2e
test-e2e: ## Run end-to-end tests
	@pytest tests/e2e/ -v

.PHONY: test-api
test-api: ## Test API endpoints
	@pytest tests/unit/test_api.py -v

# ============================================================================
# CODE QUALITY
# ============================================================================
.PHONY: lint
lint: ## Run linter
	@echo "Running linter..."
	@python -m ruff check . || true

.PHONY: format
format: ## Format code
	@echo "Formatting code..."
	@python -m ruff format .

.PHONY: type-check
type-check: ## Run type checker
	@echo "Running type checker..."
	@python -m mypy .

# ============================================================================
# ML WORKFLOWS
# ============================================================================
.PHONY: train
train: ## Run training job (manual trigger)
	@echo "Starting training job..."
	@docker exec kol-trainer python -m models.registry.model_versioning

.PHONY: train-trust
train-trust: ## Train trust model
	@docker exec kol-trainer python -m models.trust.train_xgb

.PHONY: train-success
train-success: ## Train success model
	@docker exec kol-trainer python -m models.success.train_lgbm

.PHONY: serve
serve: ## Run API locally (for development)
	@uvicorn serving.api.main:app --reload --port 8080

# ============================================================================
# MONITORING
# ============================================================================
.PHONY: health
health: ## Check health of all services
	@echo "Checking service health..."
	@curl -f http://localhost:9000/minio/health/live && echo "✓ MinIO" || echo "✗ MinIO"
	@curl -f http://localhost:8080/v1/info && echo "✓ Trino" || echo "✗ Trino"
	@curl -f http://localhost:8081/health && echo "✓ Airflow" || echo "✗ Airflow"
	@curl -f http://localhost:5000/health && echo "✓ MLflow" || echo "✗ MLflow"
	@curl -f http://localhost:8080/healthz && echo "✓ API" || echo "✗ API"

.PHONY: stats
stats: ## Show Docker stats
	@docker stats --no-stream

# ============================================================================
# DEPRECATED (for backward compatibility)
# ============================================================================
.PHONY: dev-up-old
dev-up-old: ## Start using old docker-compose.yml (deprecated)
	@echo "WARNING: Using deprecated docker-compose.yml"
	@docker compose -f $(COMPOSE_OLD) up -d --build

.PHONY: dev-down-old
dev-down-old: ## Stop using old docker-compose.yml (deprecated)
	@docker compose -f $(COMPOSE_OLD) down -v

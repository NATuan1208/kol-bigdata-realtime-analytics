# 🚀 Quick Start Guide — KOL Platform

## Prerequisites Check

Before starting, ensure you have:
- [ ] Docker Desktop installed (version 20.10+)
- [ ] Docker Compose V2 (comes with Docker Desktop)
- [ ] At least **8GB RAM** allocated to Docker
- [ ] At least **20GB free disk space**
- [ ] PowerShell or Bash terminal

Check your Docker version:
```powershell
docker --version
docker compose version
```

---

## 🏃 5-Minute Quick Start

### Step 1: Initialize the Project

```powershell
# Navigate to project directory
cd "d:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\Bigdata_IE212\DoAn\kol-platform"

# Create environment files
make init

# This creates:
# - .env.base.local (copy of .env.base)
# - .env.kol.local (copy of .env.kol)
# - Empty data/, notebooks/, logs/ directories
```

### Step 2: Create Docker Network

```powershell
make network-create
```

Expected output:
```
Creating shared network: data-platform-net...
```

### Step 3: Start the Infrastructure

**Option A: Start Everything (Recommended for first time)**
```powershell
make up-kol
```

This will start:
- Base platform: MinIO, PostgreSQL, Trino, Airflow, Hive Metastore, dbt
- KOL stack: Redpanda, Flink, Spark, MLflow, Cassandra, Redis, API, Trainer

**Option B: Start Gradually (If you have limited resources)**
```powershell
# First, start base platform
make up-base

# Wait 2-3 minutes for services to be healthy
# Then start KOL stack
make up-kol-only
```

### Step 4: Wait for Services to Initialize

This takes **3-5 minutes** for all services to be healthy.

Monitor progress:
```powershell
# Check service status
make ps-all

# Watch logs
make logs-kol
```

### Step 5: Verify Installation

```powershell
# Health check all services
make health
```

Expected output:
```
✓ MinIO
✓ Trino
✓ Airflow
✓ MLflow
✓ API
```

### Step 6: Initialize Data Infrastructure

```powershell
# Create MinIO buckets
make init-buckets

# Create Kafka topics
make init-topics

# Create Cassandra keyspace & tables
docker exec -i kol-cassandra cqlsh < infra/scripts/init-cassandra.cql
```

---

## 🌐 Access Services

Once everything is running, access the web UIs:

| Service | URL | Credentials |
|---------|-----|-------------|
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin123 |
| **Trino UI** | http://localhost:8080 | User: trino |
| **Airflow** | http://localhost:8081 | admin / admin123 |
| **Redpanda Console** | http://localhost:8082 | No auth |
| **Flink JobManager** | http://localhost:8083 | No auth |
| **Spark Master** | http://localhost:8084 | No auth |
| **MLflow** | http://localhost:5000 | No auth |
| **Inference API** | http://localhost:8080 | No auth (dev) |
| **Jupyter Lab** | http://localhost:8888 | No token (dev) |

---

## 🧪 Test the API

### Health Check
```powershell
curl http://localhost:8080/healthz
```

Expected response:
```json
{"ok": true}
```

### API Documentation
Open in browser:
```
http://localhost:8080/docs
```

This shows the interactive Swagger UI with all API endpoints.

---

## 📊 Explore the Data Platform

### Query with Trino

```powershell
# Open Trino CLI
docker exec -it base-trino trino

# List catalogs
SHOW CATALOGS;

# List schemas
SHOW SCHEMAS FROM iceberg;

# Create a test table
CREATE TABLE iceberg.silver.test_table (
    id INTEGER,
    name VARCHAR,
    created_at TIMESTAMP
);
```

### Check Kafka Topics

```powershell
# List topics
docker exec kol-redpanda rpk topic list

# Produce a test message
docker exec kol-redpanda rpk topic produce events.social.raw

# Consume messages
docker exec kol-redpanda rpk topic consume events.social.raw --num 10
```

### Query Cassandra

```powershell
# Open CQL shell
docker exec -it kol-cassandra cqlsh

# Use keyspace
USE kol_metrics;

# Describe tables
DESCRIBE TABLES;

# Query table
SELECT * FROM kol_realtime_metrics LIMIT 10;
```

### Check Redis Cache

```powershell
# Open Redis CLI
docker exec -it kol-redis redis-cli

# List keys
KEYS *

# Get a value
GET some_key

# Monitor commands
MONITOR
```

---

## 🔧 Common Operations

### View Logs

```powershell
# All KOL services
make logs-kol

# Specific service
make logs-api
make logs-trainer
make logs-flink

# Base platform
make logs-base
```

### Restart Services

```powershell
# Restart KOL stack
make restart-kol

# Restart base platform
make restart-base
```

### Execute Commands in Containers

```powershell
# API container
make exec-api

# Trainer container
make exec-trainer

# PostgreSQL
make exec-postgres

# Redis
make exec-redis

# Cassandra
make exec-cassandra
```

### Stop Services

```powershell
# Stop KOL stack only
make down-kol

# Stop everything
make down-all
```

---

## 🚨 Troubleshooting

### Services Not Starting?

1. **Check Docker resources**:
   ```powershell
   docker info
   ```
   Ensure you have at least 8GB RAM allocated.

2. **Check logs**:
   ```powershell
   make logs-kol
   ```

3. **Verify network**:
   ```powershell
   docker network ls | grep data-platform-net
   ```

### Port Conflicts?

If you see "port already in use" errors:

1. **Find what's using the port**:
   ```powershell
   netstat -ano | findstr :8080
   ```

2. **Change the port in `.env.kol`**:
   ```ini
   API_PORT=8090
   ```

3. **Restart**:
   ```powershell
   make restart-kol
   ```

### Out of Memory?

1. **Increase Docker Desktop memory** to 12GB or more
2. **Reduce worker replicas** in `docker-compose.kol.yml`
3. **Stop unnecessary services**

### Health Check Failures?

Wait a bit longer (services take 3-5 minutes to fully initialize), then check:
```powershell
make health
docker ps --filter health=unhealthy
```

---

## 📚 Next Steps

After successfully starting the infrastructure:

1. **Read the Project Roadmap**: [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)
2. **Explore the Architecture**: [KOL_Architecture_Ensemble.md](KOL_Architecture_Ensemble.md)
3. **Review Implementation Tasks**: [COPILOT_TASKS.md](COPILOT_TASKS.md)
4. **Start Development**: Follow Phase 1 tasks in roadmap

---

## 🆘 Getting Help

- **Infrastructure docs**: [INFRASTRUCTURE.md](INFRASTRUCTURE.md)
- **Architecture docs**: [KOL_Architecture_Ensemble.md](KOL_Architecture_Ensemble.md)
- **Project roadmap**: [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)

---

**Congratulations! Your KOL Platform infrastructure is now running! 🎉**

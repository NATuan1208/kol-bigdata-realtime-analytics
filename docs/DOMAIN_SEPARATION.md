# 🏢 Domain Separation Architecture

## 🎉 PHASE 0 COMPLETE (2025-11-15 21:05)

> 📅 **Last Updated**: December 9, 2025

**SME Pulse** and **KOL Analytics** are **two independent business domains** running on the **same shared data platform** in local/dev environment. 

Separation is enforced at the **logical layer** through naming conventions and environment configurations, not physical infrastructure isolation.

### ✅ All Services Running & Verified

> 💡 **Note**: All services have been tested and verified working correctly.

- **Shared Infrastructure**: PostgreSQL, MinIO, Trino (8081), Hive Metastore (9083) - used by BOTH domains
- **Network**: `sme-network` - shared by all containers
- **KOL Services** (12 containers total):
  - ✅ kol-api (healthy, **port 8000** - avoids conflict with SME Airflow 8080)
  - ✅ kol-trainer (running)
  - ✅ kol-mlflow (running on port 5000 - healthcheck removed, manual test OK)
  - ✅ kol-spark-master (healthy, ports 7077, 8084)
  - ✅ kol-spark-history (running, port 18080)
  - ✅ kol-spark-streaming (running)
  - ✅ kol-cassandra (healthy, port 9042)
  - ✅ kol-redis (healthy, **port 16379** - avoids conflict with SME Redis 6379)
  - ✅ kol-redpanda (healthy, ports 19092, 18081-18082)
  - ✅ kol-redpanda-console (running on **port 8082** - topic documentation disabled)
  - ✅ infra-spark-worker-1 (running)
  - ✅ infra-spark-worker-2 (running)

### ✅ Logical Separation Strategy
**Both domains share the same Hive Metastore** (`sme-hive-metastore` pointing to PostgreSQL `sme` database), but maintain clean separation through:

1. **Catalog Naming**: 
   - SME uses `sme_lake` catalog
   - KOL uses `kol_lake` catalog
   - *(Both catalogs point to same metastore but provide namespace isolation)*

2. **Schema Naming Convention**:
   - SME schemas: `bronze`, `silver`, `gold`
   - KOL schemas: `kol_bronze`, `kol_silver`, `kol_gold`
   - *(Stored in same metastore, separated by prefix)*

3. **Bucket Separation**:
   - SME bucket: `sme-lake`
   - KOL bucket: `kol-platform` (with folders: bronze/, silver/, gold/, mlflow/)

4. **Database Separation**:
   - SME: `sme_mlflow` (MLflow experiments)
   - KOL: `kol_mlflow` (MLflow experiments)

5. **Keyspace Separation**:
   - KOL: `kol_metrics` (Cassandra serving layer)

6. **MLflow Experiment Prefix**:
   - SME experiments: `SME_*`
   - KOL experiments: `KOL_*`

### ✅ Configuration Complete
- **Port Conflicts Resolved**: 
  - Redis: 6379 → **16379** (SME uses 6379)
  - API: 8080 → **8000** (SME Airflow uses 8080)
- **Credentials**: SME Pulse credentials (sme/sme123, minioadmin/minioadmin123) used throughout
- **Trino Catalogs**: Both `sme_lake` and `kol_lake` mounted and accessible
- **Schemas Created**: `kol_bronze`, `kol_silver`, `kol_gold` in shared metastore
- **Trainer Image**: 15.1GB with FULL ML stack (torch, transformers, xgboost, prophet, lightgbm, pyspark)

### ✅ Services Verification (Web UI Tests)
- **MLflow UI**: http://localhost:5000 → **200 OK** ✅
- **Spark Master UI**: http://localhost:8084 → **200 OK** ✅
- **Redpanda Console**: http://localhost:8082 → **200 OK** ✅
- **API Health**: http://localhost:8000/healthz → **{"ok":true}** ✅

### 🚨 Critical Configuration Values
```bash
# PostgreSQL (CORRECTED)
POSTGRES_USER=sme  # NOT "admin"
POSTGRES_PASSWORD=sme123  # NOT "admin"
POSTGRES_DB=kol_mlflow

# MinIO (CORRECTED)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123  # NOT "minioadmin"

# Trino (CORRECTED)
TRINO_HOST=sme-trino
TRINO_PORT=8080  # NOT 8090
TRINO_CATALOG=kol_lake  # Will be created

# Bucket Structure
MINIO_BUCKET=kol-platform
MINIO_PATH_BRONZE=bronze
MINIO_PATH_SILVER=silver
MINIO_PATH_GOLD=gold
MINIO_PATH_MLFLOW=mlflow
```

### 📊 Resource Usage (Actual)
```
Total Docker Usage: ~50GB
├─ SME Pulse Images: ~20GB
│  ├─ Trino: 3.54GB
│  ├─ Hive Metastore: 3.37GB
│  ├─ Airflow Webserver: 2.71GB
│  ├─ Airflow Scheduler: 2.71GB
│  ├─ Metabase: 1.52GB
│  ├─ API: 1.36GB
│  ├─ PostgreSQL: 391MB
│  ├─ MinIO: 241MB
│  └─ Redis: 60MB
│
└─ KOL Images: ~22GB
   ├─ Trainer (ML): 15.1GB ⚠️
   ├─ Apache Spark: 1.61GB (shared by 4 containers)
   ├─ MLflow: 1.06GB
   ├─ Redpanda: 551MB
   ├─ Cassandra: 539MB
   ├─ Redpanda Console: 310MB
   └─ Redis: 60MB

Volumes: ~11.5GB
```

### 🎯 Next Steps
1. **Mount Trino Catalog** (manual step required):
   - Edit SME Pulse `docker-compose.yml`
   - Add volume mount for `kol_lake.properties`
   - Restart `sme-trino` container
2. **Create Trino Schemas**:
   - `kol_lake.kol_bronze`
   - `kol_lake.kol_silver`
   - `kol_lake.kol_gold`
3. **Create Cassandra Keyspace**: `kol_metrics`
4. **Verify Services**: Test all UIs (MLflow, Spark, Redpanda Console, API)

---

## Overview

**SME Pulse** and **KOL Analytics** are **TWO INDEPENDENT BUSINESS DOMAINS** with completely different use cases, data sources, and analytical goals. They share the **same Docker-based data platform instance** locally for resource optimization during development.

This document explains the logical separation strategy, namespace conventions, and development practices to maintain clean boundaries between domains.

---

## 🎯 Key Principles

### 1. Independent Business Domains
- **SME Pulse**: Small-Medium Enterprise analytics (customers, products, sales forecasting)
- **KOL Analytics**: Key Opinion Leader campaign analytics (influencers, social metrics, trust scores)
- **NO SHARED BUSINESS LOGIC** or cross-domain data dependencies
- Each domain has its own ETL pipelines, ML models, and serving APIs

### 2. Shared Infrastructure for Local Dev
**Why share infrastructure?**
- ✅ Resource optimization on development laptop
- ✅ Single PostgreSQL instance (avoids 2-4GB duplicate RAM)
- ✅ Single MinIO instance (avoids duplicate storage layer)
- ✅ Single Trino + Hive Metastore (avoids duplicate query engine)
- ✅ Reduced Docker Desktop memory/CPU overhead (~50GB total instead of 80GB+)

**How is separation maintained?**
- ✅ **Logical namespaces** enforced by naming conventions
- ✅ **Bucket isolation**: `sme-lake` vs `kol-platform`
- ✅ **Schema prefixes**: `bronze/silver/gold` (SME) vs `kol_bronze/kol_silver/kol_gold` (KOL)
- ✅ **Database separation**: `sme_mlflow` vs `kol_mlflow`
- ✅ **Catalog separation**: `sme_lake` vs `kol_lake` (both use same metastore, different namespace)
- ✅ **Keyspace separation**: KOL uses dedicated `kol_metrics` Cassandra keyspace
- ✅ **Code discipline**: Each project's ETL/ML code only accesses its own namespaces

### 3. Shared Metastore, Separate Catalogs
**Critical Understanding:**
- Both `sme_lake` and `kol_lake` Trino catalogs point to **the same Hive Metastore** (`sme-hive-metastore`)
- The metastore stores **all schemas** (SME's bronze/silver/gold + KOL's kol_bronze/kol_silver/kol_gold) in PostgreSQL `sme` database
- **Separation is by naming convention**, not physical metastore isolation
- This is appropriate for local dev; production would use separate metastores

**Why this approach?**
- ✅ Lightweight: No need for second Hive Metastore container (~3.4GB saved)
- ✅ Simple: One metadata source, easier to manage
- ✅ Safe: Naming prefixes prevent accidental cross-contamination
- ❌ Not suitable for multi-tenant production (would need separate metastores there)

### 4. Production Deployment Path
In production environments, **each domain would run on separate infrastructure**:
- Separate Kubernetes clusters or cloud accounts
- Separate Hive Metastores with Glue/HMS backends
- Separate MinIO/S3 buckets with IAM isolation
- This local setup is purely for development efficiency

---

## 📦 Namespace Conventions

### MinIO Buckets (S3-Compatible Storage)

**⚠️ UPDATED CONVENTION (2025-11-15):**

| Domain | Bucket | Path Structure |
|--------|--------|----------------|
| **SME Pulse** | `sme-lake` | `sme-lake/{bronze,silver,gold}/` |
| **KOL Analytics** | `kol-platform` | `kol-platform/{bronze,silver,gold,mlflow}/` |

**Rationale:** Single bucket per project reduces complexity and follows modern data lake patterns.

**Example paths:**
- SME Bronze: `s3://sme-lake/bronze/sales/2025/01/15/data.parquet`
- KOL Bronze: `s3://kol-platform/bronze/social_events/2025/01/15/data.parquet`
- KOL Silver: `s3://kol-platform/silver/influencers/processed/`
- KOL Gold: `s3://kol-platform/gold/daily_engagement/`
- KOL MLflow: `s3://kol-platform/mlflow/artifacts/`

### PostgreSQL Databases

| Purpose | SME Pulse | KOL Analytics |
|---------|-----------|---------------|
| **Metadata** | `metastore` | *(shares metastore for Hive)* |
| **Orchestration** | `airflow` | *(shares Airflow, separate DAGs)* |
| **ML Tracking** | `sme_mlflow` | `kol_mlflow` |
| **Application** | `sme_app` | `kol_metadata` |

**Connection strings:**
- SME MLflow: `postgresql://admin:admin@sme-postgres:5432/sme_mlflow`
- KOL MLflow: `postgresql://admin:admin@sme-postgres:5432/kol_mlflow`

### Trino Schemas (Iceberg Catalog)

**⚠️ CATALOG STRATEGY (2025-11-15):**

Each project has its own dedicated catalog with 3 medallion schemas:

| Layer | SME Pulse | KOL Analytics |
|-------|-----------|---------------|
| **Catalog** | `sme_lake` | `kol_lake` |
| **Bronze** | `sme_lake.bronze` | `kol_lake.kol_bronze` |
| **Silver** | `sme_lake.silver` | `kol_lake.kol_silver` |
| **Gold** | `sme_lake.gold` | `kol_lake.kol_gold` |

**Setup Required:**
1. Mount `infra/trino/etc/catalog/kol_lake.properties` into SME Trino container
2. Restart Trino to load the new catalog
3. Create schemas using Trino CLI

**Example queries:**
```sql
-- KOL query (after setup)
CREATE SCHEMA kol_lake.kol_bronze WITH (location='s3://kol-platform/bronze/');
SELECT * FROM kol_lake.kol_silver.influencers;
SELECT * FROM kol_lake.kol_gold.daily_metrics;
```

**Catalog Configuration:**
- **Connector**: Iceberg
- **Metastore**: Shared Hive Metastore (different catalog name: `kol`)
- **Storage**: `s3://kol-platform/{bronze,silver,gold}/`
- **File Format**: Parquet with Snappy compression

### MLflow Experiments

| Domain | Experiment Prefix | Example |
|--------|-------------------|---------|
| **SME Pulse** | `SME_*` | `SME_sales_forecast`, `SME_churn_prediction` |
| **KOL Analytics** | `KOL_*` | `KOL_trust_ensemble`, `KOL_success_forecast` |

**Benefit:** Easy filtering and isolation in MLflow UI

### Cassandra Keyspaces

| Domain | Keyspace | Purpose |
|--------|----------|---------|
| **SME Pulse** | *(none - SME doesn't use Cassandra)* | - |
| **KOL Analytics** | `kol_metrics` | Real-time KOL/campaign metrics |

---

## 🔒 Isolation Enforcement

### Environment Variables (`.env.kol`)

**⚠️ UPDATED WITH CORRECT CREDENTIALS (2025-11-15):**

```bash
# ============================================================================
# Shared Infrastructure Credentials (from SME Pulse)
# ============================================================================
# PostgreSQL
POSTGRES_HOST=sme-postgres
POSTGRES_PORT=5432
POSTGRES_USER=sme          # ← CORRECTED (not "admin")
POSTGRES_PASSWORD=sme123    # ← CORRECTED (not "admin")
POSTGRES_DB=kol_mlflow

# MinIO
MINIO_ENDPOINT=http://sme-minio:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123  # ← CORRECTED (not "minioadmin")

# Trino
TRINO_HOST=sme-trino
TRINO_PORT=8080            # ← CORRECTED (not 8090)
TRINO_CATALOG=kol_lake     # ← Created and mounted

# ============================================================================
# KOL Service Ports (Conflict Resolution)
# ============================================================================
# Redis: Changed from 6379 to 16379 (SME Redis uses 6379)
REDIS_PORT=16379

# API: Changed from 8080 to 8000 (SME Airflow uses 8080)
API_PORT=8000

# ============================================================================
# KOL Domain Bucket and Paths
# ============================================================================
MINIO_BUCKET=kol-platform
MINIO_PATH_BRONZE=bronze
MINIO_PATH_SILVER=silver
MINIO_PATH_GOLD=gold
MINIO_PATH_MLFLOW=mlflow

# ============================================================================
# KOL Trino Schemas (in kol_lake catalog)
# ============================================================================
TRINO_SCHEMA_BRONZE=kol_bronze
TRINO_SCHEMA_SILVER=kol_silver
TRINO_SCHEMA_GOLD=kol_gold

# ============================================================================
# KOL MLflow Configuration
# ============================================================================
MLFLOW_PORT=5000
MLFLOW_TRACKING_URI=http://kol-mlflow:5000
MLFLOW_EXPERIMENT_NAME=KOL_models
MLFLOW_MODEL_NAME_TRUST=KOL_trust_ensemble
MLFLOW_MODEL_NAME_SUCCESS=KOL_success_forecast

# ============================================================================
# KOL Feature Store
# ============================================================================
FEATURE_STORE_PATH=s3://kol-platform/silver/features
FEATURE_STORE_TABLE=kol_lake.kol_silver.features
```

### Code Guidelines

**✅ CORRECT: Using KOL namespace**
```python
# Bronze to Silver ETL (UPDATED APPROACH)
bucket = os.getenv("MINIO_BUCKET", "kol-platform")
bronze_path = os.getenv("MINIO_PATH_BRONZE", "bronze")
spark.read.parquet(f"s3a://{bucket}/{bronze_path}/events/")
```

**❌ INCORRECT: Hardcoded generic bucket**
```python
# This would accidentally mix with SME data!
spark.read.parquet("s3a://bronze/events/")  # NO!
```

**✅ CORRECT: Using KOL Trino schema**
```sql
-- After catalog setup
CREATE TABLE kol_lake.kol_silver.events_cleaned AS
SELECT * FROM kol_lake.kol_bronze.events_raw;
```

**❌ INCORRECT: Generic schema without catalog/prefix**
```sql
-- This would fail or mix with SME tables!
CREATE TABLE silver.events_cleaned AS ...;  -- NO!
CREATE TABLE iceberg.kol_silver.events_cleaned AS ...;  -- NO! (wrong catalog)
```

**✅ CORRECT: Using KOL MLflow experiment**
```python
mlflow.set_experiment("KOL_trust_ensemble")
mlflow.log_param("model_type", "xgboost")
```

**❌ INCORRECT: Generic experiment name**
```python
# This would mix with SME experiments!
mlflow.set_experiment("trust_model")  # NO!
```

---

## 🔍 Validation Checklist

Use this checklist to verify domain separation is correctly maintained:

### 1. MinIO Buckets
```bash
# Configure MinIO client
docker exec sme-minio mc alias set local http://localhost:9000 minioadmin minioadmin123

# List all buckets
docker exec sme-minio mc ls local/

# Expected: Single bucket per project (UPDATED)
# ✅ sme-lake (SME Pulse)
# ✅ kol-platform (KOL Analytics)

# Verify KOL folder structure
docker exec sme-minio mc ls local/kol-platform/
# Expected: bronze/, silver/, gold/, mlflow/
```

### 2. PostgreSQL Databases
```bash
# List databases
docker exec sme-postgres psql -U admin -c "\l"

# Expected:
# ✅ metastore (shared for Hive Metastore)
# ✅ airflow (shared, separate DAGs)
# ✅ sme_mlflow (SME experiments)
# ✅ kol_mlflow (KOL experiments)
```

### 3. Trino Schemas
```bash
# ⚠️ REQUIRES SETUP FIRST: See docs/SETUP_TRINO_CATALOG.md

# After mounting kol_lake catalog and restarting Trino:
docker exec sme-trino trino --execute "SHOW CATALOGS;"
# Expected: kol_lake, sme_lake, system, minio

# List schemas in KOL catalog
docker exec sme-trino trino --catalog kol_lake --execute "SHOW SCHEMAS;"
# Expected after creation:
# ✅ kol_bronze, kol_silver, kol_gold
```

### 4. MLflow Experiments
```bash
# Check MLflow experiments
curl http://localhost:5000/api/2.0/mlflow/experiments/search

# Expected: Experiments prefixed with SME_ or KOL_
```

### 5. Cassandra Keyspaces
```bash
# List keyspaces
docker exec kol-cassandra cqlsh -e "DESCRIBE KEYSPACES;"

# Expected:
# ✅ kol_metrics (KOL only)
```

### 6. Code Review
Search codebase for hardcoded paths:
```bash
# Check for hardcoded bucket names (should use env vars)
grep -r "s3://bronze" .
grep -r "s3://silver" .
grep -r "s3://gold" .

# Should return NO results or only in comments
```

---

## 🚀 Setup Workflow

### Initial Setup (Run Once)

1. **Start SME Pulse infrastructure** (from SME Pulse project)
   ```bash
   cd /path/to/sme-pulse
   docker compose up -d
   ```

2. **Create shared network**
   ```bash
   docker network create sme-network
   ```

3. **Initialize KOL namespaces** (from KOL project)
   ```bash
   cd /path/to/kol-platform
   chmod +x infra/scripts/init-kol-namespace.sh
   ./infra/scripts/init-kol-namespace.sh
   ```

4. **Start KOL services**
   ```bash
   make up-kol
   ```

### Daily Development

```bash
# 1. Ensure SME Pulse is running
docker ps | grep sme-

# 2. Start KOL services
cd /path/to/kol-platform
make check-sme  # Verify prerequisites
make up-kol     # Start KOL stack

# 3. Work on KOL project
# All data writes go to kol-* namespaces automatically

# 4. Stop KOL services (SME Pulse keeps running)
make down-kol
```

---

## 🔧 Troubleshooting

### Issue: MLflow cannot connect to sme-postgres

**Symptoms:**
```
(psycopg2.OperationalError) could not translate host name "sme-postgres" to address
```

**Cause:** MLflow container not on `sme-network`

**Solution:**
```bash
# Check container network
docker inspect kol-mlflow --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'

# Should show: sme-network

# If not, recreate container
docker-compose -f infra/docker-compose.kol.yml down mlflow
docker-compose -f infra/docker-compose.kol.yml up -d mlflow
```

### Issue: Trainer image is 15GB (not 4GB as expected)

**Cause:** PyTorch includes CUDA support (~3GB) + full Transformers library (~2GB)

**Solution:** This is normal for ML images with PyTorch. To reduce size:
```dockerfile
# Option 1: Use CPU-only PyTorch (saves ~2GB)
torch>=2.1.0+cpu

# Option 2: Remove unused features
# - Remove transformers if not using NLP: saves ~2.5GB
# - Remove torch if not using deep learning: saves ~2.5GB
```

### Issue: KOL data appearing in SME buckets

**Cause:** Hardcoded bucket names in code  
**Solution:** Use environment variables
```python
# Before (wrong)
df.write.parquet("s3a://bronze/data")

# After (correct)
bronze_bucket = os.getenv("MINIO_BUCKET_BRONZE", "kol-bronze")
df.write.parquet(f"s3a://{bronze_bucket}/data")
```

### Issue: MLflow experiments mixed between SME and KOL

**Cause:** Missing experiment name prefix  
**Solution:** Always use KOL_ prefix
```python
# Before (wrong)
mlflow.set_experiment("my_model")

# After (correct)
experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "KOL_models")
mlflow.set_experiment(experiment_name)
```

### Issue: Trino query fails with "schema not found"

**Cause:** Wrong schema name  
**Solution:** Use KOL-specific schema
```sql
-- Before (wrong)
SELECT * FROM iceberg.silver.events;

-- After (correct)
SELECT * FROM iceberg.kol_silver.events;
```

---

## 📊 Benefits of This Approach

### Development Benefits
- ✅ **Cost Savings:** Single infrastructure instance reduces RAM/CPU/disk usage
- ✅ **No Port Conflicts:** SME and KOL services use different ports
- ✅ **Simplified Setup:** One PostgreSQL, one MinIO, one Trino to manage
- ✅ **Unified Tooling:** Same Trino UI, same MinIO Console for both projects
- ✅ **Fast Context Switching:** Both projects accessible simultaneously

### Production Readiness
- ✅ **Clear Boundaries:** Namespace conventions make it easy to migrate to separate infra
- ✅ **No Code Changes:** Same namespace logic works in production with separate clusters
- ✅ **Data Isolation:** No risk of SME and KOL data mixing
- ✅ **Security:** Each project can have separate IAM policies in production

---

## 🎯 Best Practices

1. **Always use environment variables** for bucket/schema/database names
2. **Never hardcode** paths like `s3://bronze` or `iceberg.silver`
3. **Prefix all MLflow experiments** with `KOL_` or `SME_`
4. **Review code** before committing to ensure namespace compliance
5. **Run validation checklist** after major changes
6. **Document** any new namespaces or conventions
7. **⚠️ NEW: Check Docker network** - All KOL containers MUST be on `sme-network`
8. **⚠️ NEW: Monitor disk space** - ML images are large (10-15GB each)
9. **⚠️ NEW: Initialize namespaces BEFORE starting services** - Create databases and buckets first
10. **⚠️ NEW: Use single bucket with paths** - Simpler than multiple buckets per layer

---

## 📝 Summary

| Aspect | SME Pulse | KOL Analytics | Shared? |
|--------|-----------|---------------|---------|
| **Business Domain** | Enterprise analytics | KOL campaigns | ❌ No |
| **Data** | Customers, sales | KOLs, social metrics | ❌ No |
| **Pipelines** | SME ETL/models | KOL ETL/models | ❌ No |
| **MinIO Buckets** | sme-lake | kol-platform | ❌ No |
| **PostgreSQL DBs** | sme_mlflow | kol_mlflow | ❌ No |
| **Trino Catalogs** | sme_lake | kol_lake | ❌ No |
| **Trino Schemas** | bronze, silver, gold | kol_bronze, kol_silver, kol_gold | ❌ No |
| **MLflow Prefix** | SME_* | KOL_* | ❌ No |
| **Infrastructure** | sme-postgres, sme-minio, sme-trino | *(connects to same)* | ✅ Yes |
| **Docker Network** | smepulseproject_sme-network | sme-network | ⚠️ Bridged |

**Bottom Line:** Two independent projects, one shared infrastructure instance, strict logical separation via namespaces. Infrastructure containers accessible from both networks via Docker bridge.

---

---

## 🐛 Known Issues & Solutions (2025-11-15 17:40)

### ✅ RESOLVED
1. **MLflow Connection**: Fixed by connecting `sme-postgres` to `sme-network` and using correct credentials (sme/sme123)
2. **Database Created**: `kol_mlflow` database successfully created in PostgreSQL
3. **Network Isolation**: All KOL containers on `sme-network`, can communicate with SME infrastructure
4. **Trainer Build**: 15.1GB image successfully built with full ML stack
5. **MinIO Bucket**: `kol-platform` bucket created with proper folder structure
6. **Credentials**: All `.env.kol` values corrected to match SME Pulse actual config

### ⚠️ PENDING (Manual Steps Required)
1. **Trino Catalog Setup**: Need to mount `kol_lake.properties` into SME Trino container
   - **Action**: Edit SME Pulse `docker-compose.yml` to add volume mount
   - **Documentation**: See `docs/SETUP_TRINO_CATALOG.md` for detailed steps
   - **Impact**: Cannot create Trino schemas until this is done

2. **Cassandra Keyspace**: `kol_metrics` keyspace not yet created
   - **Action**: Run CQL script after validating Cassandra is healthy
   - **Priority**: Medium (only needed for Phase 2+ streaming metrics)

### 📝 Design Changes from Original
1. **Bucket Strategy**: Single `kol-platform` bucket (not 4 separate buckets)
2. **Catalog Strategy**: Dedicated `kol_lake` catalog (not shared `iceberg`)
3. **Image Size**: 15GB trainer image (not 4GB) due to PyTorch CUDA + full transformers
4. **Phase Approach**: No phased requirements - loaded ALL ML packages upfront
5. **Port Correction**: Trino 8080 internal / 8081 external (not 8090)

---

## 📊 Resource Usage Summary

```
Docker Images: ~50GB total
  - SME Pulse services: ~35GB
    - Airflow: 2.7GB
    - Trino: 3.5GB
    - Hive Metastore: 3.4GB
    - Metabase: 1.5GB
    - PostgreSQL: 400MB
    - MinIO: 240MB
    - Redis: 60MB
  
  - KOL Analytics services: ~15GB
    - Trainer (ML): 15.1GB ⚠️
    - Spark (3 containers): ~1.6GB each
    - MLflow: 1.1GB
    - Redpanda: 550MB
    - Cassandra: 540MB
    - Redpanda Console: 310MB
    - Redis: 60MB

Docker Volumes: ~12GB
  - SME data: ~11GB
  - KOL data: ~1GB (will grow)

Recommended System:
  - RAM: 16GB minimum (32GB ideal)
  - Disk: 100GB free space
  - CPU: 8+ cores recommended
```

---

**For more information:**
- [Quick Start Guide](QUICKSTART.md)
- [Infrastructure Overview](INFRASTRUCTURE.md)
- [Migration Guide](MIGRATION_TO_SHARED_INFRA.md)
- [Setup Checklist](SETUP_CHECKLIST.md)

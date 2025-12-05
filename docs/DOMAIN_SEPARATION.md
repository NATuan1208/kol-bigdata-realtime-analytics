# 🏢 Domain Separation Architecture

## Overview

**SME Pulse** and **KOL Analytics** are **TWO COMPLETELY INDEPENDENT PROJECTS** with different business domains, data, and pipelines. They **ONLY SHARE** the same Docker-based infrastructure **INSTANCE** locally for resource optimization during development.

This document explains the separation philosophy, namespace conventions, and validation procedures.

---

## 🎯 Key Principles

### 1. Independent Domains
- **SME Pulse**: Small-Medium Enterprise analytics (customers, products, sales)
- **KOL Analytics**: Key Opinion Leader campaigns (influencers, social metrics, trust scores)
- **NO SHARED BUSINESS LOGIC** or data between the two
- Think of them as "two companies sharing one datacenter"

### 2. Shared Infrastructure Instance (Local Dev Only)
- **Why share?** Resource optimization on development laptop:
  - ✅ Single PostgreSQL instance (avoids duplicate RAM usage)
  - ✅ Single MinIO instance (avoids duplicate storage)
  - ✅ Single Trino instance (avoids duplicate query engine)
  - ✅ No port conflicts between projects
  - ✅ Reduced Docker Desktop memory/CPU overhead

- **How is separation maintained?** Logical namespaces:
  - Different MinIO buckets
  - Different PostgreSQL databases
  - Different Trino schemas
  - Different MLflow experiment prefixes
  - Different Cassandra keyspaces (KOL-only service)

### 3. Production Deployment
In production, **each project would run on separate infrastructure clusters**. This local dev setup is purely for convenience and cost savings during development.

---

## 📦 Namespace Conventions

### MinIO Buckets (S3-Compatible Storage)

| Layer | SME Pulse | KOL Analytics |
|-------|-----------|---------------|
| **Bronze** (Raw) | `sme-bronze` | `kol-bronze` |
| **Silver** (Cleaned) | `sme-silver` | `kol-silver` |
| **Gold** (Aggregated) | `sme-gold` | `kol-gold` |
| **ML Artifacts** | `sme-mlflow` | `kol-mlflow` |

**Example paths:**
- SME: `s3://sme-bronze/sales/2025/01/15/data.parquet`
- KOL: `s3://kol-bronze/social_events/2025/01/15/data.parquet`

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

| Layer | SME Pulse | KOL Analytics |
|-------|-----------|---------------|
| **Bronze** | `iceberg.sme_bronze` | `iceberg.kol_bronze` |
| **Silver** | `iceberg.sme_silver` | `iceberg.kol_silver` |
| **Gold** | `iceberg.sme_gold` | `iceberg.kol_gold` |

**Example queries:**
```sql
-- SME query
SELECT * FROM iceberg.sme_gold.customer_metrics;

-- KOL query
SELECT * FROM iceberg.kol_gold.kol_trust_scores;
```

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

```bash
# KOL Domain Bucket Namespaces
MINIO_BUCKET_BRONZE=kol-bronze
MINIO_BUCKET_SILVER=kol-silver
MINIO_BUCKET_GOLD=kol-gold
MINIO_BUCKET_MLFLOW=kol-mlflow

# KOL Database
POSTGRES_DB=kol_mlflow

# KOL Trino Schemas
TRINO_SCHEMA_BRONZE=kol_bronze
TRINO_SCHEMA_SILVER=kol_silver
TRINO_SCHEMA_GOLD=kol_gold

# KOL MLflow Prefix
MLFLOW_EXPERIMENT_NAME=KOL_models
MLFLOW_MODEL_NAME_TRUST=KOL_trust_ensemble
MLFLOW_MODEL_NAME_SUCCESS=KOL_success_forecast

# KOL Feature Store
FEATURE_STORE_PATH=s3://kol-silver/features
FEATURE_STORE_TABLE=iceberg.kol_silver.features
```

### Code Guidelines

**✅ CORRECT: Using KOL namespace**
```python
# Bronze to Silver ETL
bronze_bucket = os.getenv("MINIO_BUCKET_BRONZE", "kol-bronze")
spark.read.parquet(f"s3a://{bronze_bucket}/events/")
```

**❌ INCORRECT: Hardcoded generic bucket**
```python
# This would accidentally mix with SME data!
spark.read.parquet("s3a://bronze/events/")  # NO!
```

**✅ CORRECT: Using KOL Trino schema**
```sql
CREATE TABLE iceberg.kol_silver.events_cleaned AS
SELECT * FROM iceberg.kol_bronze.events_raw;
```

**❌ INCORRECT: Generic schema without prefix**
```sql
-- This would mix with SME tables!
CREATE TABLE iceberg.silver.events_cleaned AS ...;  -- NO!
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
# List all buckets
docker exec sme-minio mc ls local/

# Expected: Separate SME and KOL buckets
# ✅ sme-bronze, sme-silver, sme-gold
# ✅ kol-bronze, kol-silver, kol-gold, kol-mlflow
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
# List Iceberg schemas
docker exec sme-trino trino --execute "SHOW SCHEMAS IN iceberg;"

# Expected:
# ✅ sme_bronze, sme_silver, sme_gold
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

---

## 📝 Summary

| Aspect | SME Pulse | KOL Analytics | Shared? |
|--------|-----------|---------------|---------|
| **Business Domain** | Enterprise analytics | KOL campaigns | ❌ No |
| **Data** | Customers, sales | KOLs, social metrics | ❌ No |
| **Pipelines** | SME ETL/models | KOL ETL/models | ❌ No |
| **MinIO Buckets** | sme-* | kol-* | ❌ No |
| **PostgreSQL DBs** | sme_* | kol_* | ❌ No |
| **Trino Schemas** | sme_* | kol_* | ❌ No |
| **MLflow Prefix** | SME_* | KOL_* | ❌ No |
| **Infrastructure** | sme-postgres, sme-minio, sme-trino | *(connects to same)* | ✅ Yes |

**Bottom Line:** Two independent projects, one shared infrastructure instance, strict logical separation via namespaces.

---

**For more information:**
- [Quick Start Guide](QUICKSTART.md)
- [Infrastructure Overview](INFRASTRUCTURE.md)
- [Migration Guide](MIGRATION_TO_SHARED_INFRA.md)

# KOL Analytics Setup Checklist

Quick reference for setting up KOL Analytics on shared infrastructure with strict domain separation.

> 📘 **Full Documentation**: See [DOMAIN_SEPARATION.md](DOMAIN_SEPARATION.md) for comprehensive details.

---

## Prerequisites

✅ **SME Pulse Infrastructure Running**
```bash
cd /path/to/sme-pulse
make up
```

Verify services at:
- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
- PostgreSQL: localhost:5432
- Trino UI: http://localhost:8080
- Airflow UI: http://localhost:8081

---

## Step 1: Initialize KOL Namespaces

```bash
cd /path/to/kol-platform
make init-kol-namespace
```

**What this creates:**
- 📦 MinIO buckets: `kol-bronze`, `kol-silver`, `kol-gold`, `kol-mlflow`
- 🗄️ PostgreSQL DBs: `kol_mlflow`, `kol_metadata`
- 📊 Trino schemas: `iceberg.kol_bronze`, `kol_silver`, `kol_gold`
- 💾 Cassandra keyspace: `kol_metrics`

**Manual verification:**
```bash
# Check MinIO buckets
mc ls local/

# Check PostgreSQL databases
docker exec -it sme-postgres psql -U admin -d postgres -c "\l"

# Check Trino schemas
docker exec -it sme-trino trino --catalog iceberg --execute "SHOW SCHEMAS;"

# Check Cassandra keyspace
docker exec -it kol-cassandra cqlsh -e "DESCRIBE KEYSPACES;"
```

---

## Step 2: Start KOL Services

```bash
make up-kol
```

**KOL-specific services:**
- 🔴 Redpanda (Kafka): localhost:19092, Console at http://localhost:8082
- ⚡ Spark Master: http://localhost:8083
- 📈 MLflow UI: http://localhost:5000
- 💾 Cassandra: localhost:9042
- 🔴 Redis: localhost:6379
- 🎯 Trainer: Batch ML training service
- 🚀 API: FastAPI at http://localhost:8000

---

## Step 3: Validate Separation

```bash
make validate-separation
```

**Expected output:**
```
[PASS] MinIO buckets exist (kol-bronze, kol-silver, kol-gold, kol-mlflow)
[PASS] PostgreSQL databases exist (kol_mlflow, kol_metadata)
[PASS] Trino schemas exist (iceberg.kol_bronze, kol_silver, kol_gold)
[PASS] Cassandra keyspace exists (kol_metrics)
[PASS] .env.kol has KOL namespace variables
[PASS] No hardcoded SME paths in code
[PASS] docker-compose.kol.yml uses kol_mlflow
========================================
VALIDATION SUMMARY: All checks passed!
```

---

## Step 4: Run Sample ETL

```bash
# Bronze to Silver
docker exec -it kol-trainer python /app/batch/etl/bronze_to_silver.py

# Silver to Gold
docker exec -it kol-trainer python /app/batch/etl/silver_to_gold.py

# Build features
docker exec -it kol-trainer python /app/batch/feature_store/build_features.py
```

**Verify in Trino:**
```sql
-- Check data in Trino
SELECT * FROM iceberg.kol_silver.influencers LIMIT 10;
SELECT * FROM iceberg.kol_gold.daily_engagement LIMIT 10;
```

---

## Step 5: Train Sample Model

```bash
docker exec -it kol-trainer python /app/models/trust/train_xgb.py
```

**Verify in MLflow:**
- Open http://localhost:5000
- Check experiment: `KOL_trust_score`
- Verify artifacts in MinIO: `kol-mlflow/artifacts/`

---

## Common Commands

| Task | Command |
|------|---------|
| Start all KOL services | `make up-kol` |
| Stop all KOL services | `make down-kol` |
| View KOL logs | `make logs-kol` |
| Restart KOL services | `make restart-kol` |
| Initialize namespaces | `make init-kol-namespace` |
| Validate separation | `make validate-separation` |
| Check SME infrastructure | `make check-sme` |

---

## Troubleshooting

### ❌ Validation fails: "MinIO bucket does not exist"
```bash
# Re-run initialization
make init-kol-namespace
```

### ❌ "Connection refused" to PostgreSQL
```bash
# Check SME infrastructure is running
cd /path/to/sme-pulse
docker ps | grep sme-postgres

# Restart if needed
make restart
```

### ❌ MLflow writes to wrong bucket
```bash
# Check .env.kol
grep MINIO_BUCKET_MLFLOW .env.kol
# Should be: MINIO_BUCKET_MLFLOW=kol-mlflow

# Check docker-compose.kol.yml mlflow service
grep "s3://kol-mlflow" infra/docker-compose.kol.yml
```

### ❌ Trino query fails: "Schema does not exist"
```bash
# Verify schemas in Trino
docker exec -it sme-trino trino --catalog iceberg --execute "SHOW SCHEMAS;"

# Re-create if missing
docker exec -it sme-trino trino --catalog iceberg --execute \
  "CREATE SCHEMA IF NOT EXISTS kol_bronze WITH (location='s3a://kol-bronze/');"
```

### ❌ Code writes to SME namespace by accident
```bash
# Search for hardcoded SME paths
make validate-separation

# Common culprits:
# - Hardcoded "sme-bronze" instead of ${MINIO_BUCKET_BRONZE}
# - Hardcoded "iceberg.sme_silver" instead of f"iceberg.{TRINO_SCHEMA_SILVER}"
# - Direct "sme_mlflow" instead of ${POSTGRES_DB}
```

---

## Domain Separation Rules (Quick Reference)

| Resource Type | KOL Namespace | SME Namespace |
|---------------|---------------|---------------|
| **MinIO Buckets** | `kol-bronze`, `kol-silver`, `kol-gold`, `kol-mlflow` | `sme-bronze`, `sme-silver`, `sme-gold`, `sme-mlflow` |
| **PostgreSQL DBs** | `kol_mlflow`, `kol_metadata` | `sme_mlflow`, `sme_metastore` |
| **Trino Schemas** | `iceberg.kol_bronze`, `kol_silver`, `kol_gold` | `iceberg.sme_bronze`, `sme_silver`, `sme_gold` |
| **MLflow Experiments** | `KOL_trust_score`, `KOL_success_forecast` | `SME_churn`, `SME_lead_score` |
| **Cassandra Keyspaces** | `kol_metrics` | `sme_analytics` |

**Golden Rule**: ALWAYS use environment variables from `.env.kol`, NEVER hardcode paths!

---

## Next Steps

1. ✅ Complete this checklist
2. 📖 Read [DOMAIN_SEPARATION.md](DOMAIN_SEPARATION.md) for full philosophy
3. 🏗️ See [INFRASTRUCTURE.md](guides/INFRASTRUCTURE.md) for architecture details
4. 🚀 See [QUICKSTART.md](../QUICKSTART.md) for development workflow

---

## Verification Checklist

Before committing code, ensure:

- [ ] All paths use environment variables from `.env.kol`
- [ ] No hardcoded `sme-*` or `sme_*` strings in KOL code
- [ ] MLflow experiments use `KOL_` prefix
- [ ] Trino queries use `iceberg.kol_*` schemas
- [ ] Feature store path is `s3://kol-silver/features`
- [ ] `make validate-separation` passes all checks

---

## Help

- 🐛 **Issues**: Open GitHub issue with validation output
- 📚 **Docs**: [DOMAIN_SEPARATION.md](DOMAIN_SEPARATION.md)
- 💬 **Questions**: Check [PROJECT_ROADMAP.md](guides/PROJECT_ROADMAP.md)

---

**Last Updated**: 2025-01-XX  
**Version**: 1.0.0

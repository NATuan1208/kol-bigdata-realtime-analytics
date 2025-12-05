# Phase 1: Bronze Layer - Complete Setup Guide

## ✅ What's Done

### Step 1-3: Data Collection & Upload ✅
- ✅ 24 records collected from 3 sources
- ✅ Uploaded to MinIO Bronze (`s3://kol-platform/bronze/raw/*/dt=2025-11-16/`)

### Step 4: SQL DDL ✅
- ✅ Created `dwh/ddl/bronze_raw_tables.sql`

### Step 5: Spark Batch Job ✅  
- ✅ Created `batch/etl/load_bronze_data.py`

---

## 🚀 How to Execute Phase 1

### 1. Run SQL DDL (Create Tables)

```bash
# Connect to Trino
docker exec -it sme-trino trino --server http://localhost:8080

# Run DDL
USE kol_lake.kol_bronze;
-- Then paste content from dwh/ddl/bronze_raw_tables.sql
-- Or run from file:
```

**Alternative: Run from file**
```bash
docker exec -i sme-trino trino --server http://localhost:8080 --catalog kol_lake --schema kol_bronze < dwh/ddl/bronze_raw_tables.sql
```

### 2. Run Spark Job (Load Data)

```bash
# Inside Spark master container
docker exec -it kol-spark-master bash

# Run Spark job for all sources
spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.kol_lake=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.kol_lake.type=hive \
  --conf spark.sql.catalog.kol_lake.uri=thrift://sme-hive-metastore:9083 \
  /opt/kol-platform/batch/etl/load_bronze_data.py \
  --date 2025-11-16 \
  --source all
```

**Or load single source:**
```bash
spark-submit ... /opt/kol-platform/batch/etl/load_bronze_data.py --date 2025-11-16 --source youtube_trending
```

### 3. Verify Data in Trino

```sql
-- Check tables exist
USE kol_lake.kol_bronze;
SHOW TABLES;

-- Check record counts
SELECT 'youtube' as source, COUNT(*) FROM raw_youtube_trending WHERE dt = DATE '2025-11-16'
UNION ALL
SELECT 'wikipedia', COUNT(*) FROM raw_wikipedia_backlinko WHERE dt = DATE '2025-11-16'
UNION ALL
SELECT 'weibo', COUNT(*) FROM raw_weibo_dataset WHERE dt = DATE '2025-11-16';

-- Sample data
SELECT 
    kol_id,
    platform,
    JSON_EXTRACT_SCALAR(payload, '$.title') as title,
    ingest_ts
FROM raw_youtube_trending
WHERE dt = DATE '2025-11-16'
LIMIT 5;
```

---

## 📊 Expected Results

| Table | Records | Partition |
|-------|---------|-----------|
| `raw_youtube_trending` | 10 | `dt=2025-11-16` |
| `raw_wikipedia_backlinko` | 10 | `dt=2025-11-16` |
| `raw_weibo_dataset` | 4 | `dt=2025-11-16` |
| **TOTAL** | **24** | |

---

## 🔄 Daily Batch Pipeline (Future)

```bash
# 1. Collect data
python ingestion/batch_ingest.py --source all --limit 100 --upload

# 2. Load to Iceberg (via Airflow DAG)
spark-submit batch/etl/load_bronze_data.py --date $(date +%Y-%m-%d) --source all

# 3. Verify
trino --execute "SELECT source, COUNT(*) FROM kol_lake.kol_bronze.raw_youtube_trending WHERE dt = CURRENT_DATE GROUP BY source"
```

---

## 📁 Files Created

```
ingestion/
├── config.py                    # Config with dotenv
├── minio_client.py              # S3 upload utilities  
├── batch_ingest.py              # CLI orchestrator (358 lines)
└── sources/
    ├── youtube_trending.py      # YouTube API collector
    ├── wikipedia_backlinko.py   # Wikipedia scraper
    └── weibo_dataset.py         # Weibo CSV reader

dwh/ddl/
└── bronze_raw_tables.sql        # Iceberg DDL (3 tables)

batch/etl/
└── load_bronze_data.py          # Spark loader (292 lines)
```

---

## ✅ Phase 1 Complete!

**Next Phase**: Bronze → Silver transformation (cleaning, deduplication, enrichment)

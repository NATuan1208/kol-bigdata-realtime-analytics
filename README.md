# kol-bigdata-realtime-analytics

A real-time **KOL Trustworthiness & Success Analytics** platform built on modern Data Engineering & MLOps stack.

> ⚠️ **Bài toán**: Đánh giá **độ tin cậy KOL** (Trust Score) để hỗ trợ brands quyết định hợp tác marketing - **KHÔNG phải** bài toán Bot Detection. Dataset bot detection được sử dụng làm **PROXY** vì bot patterns ~ untrustworthy KOL patterns (~80% overlap).

## 📊 Data Pipeline Status

| Layer | Tables | Records | Status |
|-------|--------|---------|--------|
| **Bronze** (Raw) | 4 | 86,311 | ✅ Complete |
| **Silver** (Cleaned) | 4 | 125,266 | ✅ Complete |
| **Gold** (Star Schema) | 8 | 161,229 | ✅ Complete |

**Total**: 16 tables, 372,806 records processed via **PySpark on Docker cluster**

## 🏗️ Architecture

- **Medallion Architecture**: Bronze → Silver → Gold layers
- **Star Schema**: 4 dimensions + 1 fact table + ML tables
- **Processing**: PySpark 3.5.1 on Docker cluster (2 workers, 4 cores)
- **Storage**: MinIO (S3-compatible) with Parquet format
- **Query Engine**: Trino + Hive Metastore
- **Feature Engineering**: 28 engineered features for ML

📚 **Full Documentation**: [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)

## 🚀 Quick Start

```bash
# Start infrastructure
cd dwh/infra && docker-compose -f docker-compose.kol.yml up -d

# Run ETL pipeline
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py

# Query with Trino
docker exec -it sme-trino trino --execute "SELECT * FROM minio.kol_gold.agg_platform_kpi"
```

---

## Features

- Lambda Architecture with S3-based Lakehouse (Iceberg)
- Airflow pipelines for orchestration
- Trino queries for analytics
- dbt transformation
- 3-layer ensemble ML system (XGBoost + Prophet + PhoBERT)

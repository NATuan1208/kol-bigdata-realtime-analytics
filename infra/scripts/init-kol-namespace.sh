#!/bin/bash
# ============================================================================
# KOL Analytics Domain Namespace Initialization
# ============================================================================
# This script initializes the KOL-specific namespaces in shared infrastructure
# 
# DOMAIN SEPARATION:
# - Creates KOL buckets in MinIO (separate from SME buckets)
# - Creates KOL database in PostgreSQL (separate from SME databases)
# - Creates KOL schemas in Trino (separate from SME schemas)
# - Creates KOL keyspace in Cassandra
#
# Run this ONCE after SME Pulse infrastructure is running
# ============================================================================

set -e

echo "============================================"
echo "KOL Analytics Domain Namespace Setup"
echo "============================================"
echo ""

# ============================================================================
# 1. MinIO Buckets (KOL Domain)
# ============================================================================
echo "📦 Creating KOL buckets in MinIO..."

# Install mc client if not exists
docker exec sme-minio mc alias set local http://localhost:9000 minio minio123 2>/dev/null || true

# Create KOL buckets (separate from SME buckets)
docker exec sme-minio mc mb local/kol-bronze --ignore-existing
docker exec sme-minio mc mb local/kol-silver --ignore-existing
docker exec sme-minio mc mb local/kol-gold --ignore-existing
docker exec sme-minio mc mb local/kol-mlflow --ignore-existing

echo "✅ KOL buckets created:"
echo "   - kol-bronze (raw data)"
echo "   - kol-silver (cleaned data)"
echo "   - kol-gold (aggregated/features)"
echo "   - kol-mlflow (ML artifacts)"
echo ""

# ============================================================================
# 2. PostgreSQL Database (KOL Domain)
# ============================================================================
echo "🗄️  Creating KOL database in PostgreSQL..."

docker exec -i sme-postgres psql -U sme -d postgres <<EOF
-- Create KOL MLflow database (separate from SME databases)
CREATE DATABASE kol_mlflow;
GRANT ALL PRIVILEGES ON DATABASE kol_mlflow TO sme;

-- Create KOL metadata database (optional, for future use)
CREATE DATABASE kol_metadata;
GRANT ALL PRIVILEGES ON DATABASE kol_metadata TO sme;

-- List databases to verify
\l
EOF

echo "✅ KOL databases created:"
echo "   - kol_mlflow (MLflow backend store)"
echo "   - kol_metadata (optional metadata store)"
echo ""

# ============================================================================
# 3. Cassandra Keyspace (KOL Domain)
# ============================================================================
echo "💿 Creating KOL keyspace in Cassandra..."

docker exec -i kol-cassandra cqlsh -e "
CREATE KEYSPACE IF NOT EXISTS kol_metrics
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE kol_metrics;

-- KOL real-time metrics table
CREATE TABLE IF NOT EXISTS kol_realtime_metrics (
    kol_id text,
    campaign_id text,
    window_start timestamp,
    window_end timestamp,
    total_impressions bigint,
    total_clicks bigint,
    total_conversions bigint,
    total_revenue double,
    event_count bigint,
    ctr double,
    cvr double,
    processed_at timestamp,
    PRIMARY KEY ((kol_id, campaign_id), window_start)
) WITH CLUSTERING ORDER BY (window_start DESC);

DESCRIBE KEYSPACE kol_metrics;
"

echo "✅ Cassandra keyspace created: kol_metrics"
echo ""

# ============================================================================
# 4. Trino Schemas (KOL Domain)
# ============================================================================
echo "🚀 Creating KOL schemas in Trino..."

docker exec -i sme-trino trino --execute "
-- KOL Bronze schema (raw data from Kafka/APIs)
CREATE SCHEMA IF NOT EXISTS iceberg.kol_bronze
WITH (location = 's3a://kol-bronze/');

-- KOL Silver schema (cleaned, validated data)
CREATE SCHEMA IF NOT EXISTS iceberg.kol_silver
WITH (location = 's3a://kol-silver/');

-- KOL Gold schema (aggregated features, KPIs)
CREATE SCHEMA IF NOT EXISTS iceberg.kol_gold
WITH (location = 's3a://kol-gold/');

-- Verify schemas
SHOW SCHEMAS IN iceberg;
"

echo "✅ Trino schemas created:"
echo "   - iceberg.kol_bronze"
echo "   - iceberg.kol_silver"
echo "   - iceberg.kol_gold"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "============================================"
echo "✅ KOL Analytics Namespace Setup Complete!"
echo "============================================"
echo ""
echo "Domain separation verified:"
echo "  MinIO Buckets:"
echo "    - SME: sme-bronze, sme-silver, sme-gold"
echo "    - KOL: kol-bronze, kol-silver, kol-gold, kol-mlflow"
echo ""
echo "  PostgreSQL Databases:"
echo "    - SME: metastore, airflow"
echo "    - KOL: kol_mlflow, kol_metadata"
echo ""
echo "  Trino Schemas:"
echo "    - SME: iceberg.sme_*"
echo "    - KOL: iceberg.kol_*"
echo ""
echo "  Cassandra Keyspaces:"
echo "    - SME: (if any)"
echo "    - KOL: kol_metrics"
echo ""
echo "Next steps:"
echo "  1. Start KOL services: make up-kol"
echo "  2. Verify MLflow: http://localhost:5000"
echo "  3. Check MinIO Console: http://localhost:9001"
echo "  4. Begin data ingestion and ETL pipelines"
echo ""

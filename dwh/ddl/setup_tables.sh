#!/bin/bash
# ============================================================================
# KOL Platform - DDL Setup Script
# ============================================================================
# This script creates all Trino tables for the KOL Analytics Platform
# 
# Usage:
#   chmod +x setup_tables.sh
#   ./setup_tables.sh
#
# Or run manually:
#   docker exec -it sme-trino trino -f /path/to/kol_complete_ddl.sql
# ============================================================================

set -e

echo "=============================================="
echo "🗄️  KOL Platform - Setting up Trino Tables"
echo "=============================================="

# Check if Trino is running
if ! docker ps | grep -q sme-trino; then
    echo "❌ Error: sme-trino container is not running"
    echo "   Start it with: docker-compose -f dwh/infra/docker-compose.kol.yml up -d"
    exit 1
fi

echo ""
echo "📋 Creating schemas..."

# Create schemas
docker exec sme-trino trino --execute "CREATE SCHEMA IF NOT EXISTS minio.kol_bronze WITH (location = 's3a://kol-platform/bronze/')"
docker exec sme-trino trino --execute "CREATE SCHEMA IF NOT EXISTS minio.kol_silver WITH (location = 's3a://kol-platform/silver/')"
docker exec sme-trino trino --execute "CREATE SCHEMA IF NOT EXISTS minio.kol_gold WITH (location = 's3a://kol-platform/gold/')"

echo "✅ Schemas created"

echo ""
echo "📋 Current tables in each schema:"
echo ""
echo "--- BRONZE ---"
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_bronze" 2>/dev/null || echo "(empty)"

echo ""
echo "--- SILVER ---"
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_silver" 2>/dev/null || echo "(empty)"

echo ""
echo "--- GOLD ---"
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_gold" 2>/dev/null || echo "(empty)"

echo ""
echo "=============================================="
echo "📊 Table Record Counts:"
echo "=============================================="

# Bronze counts
echo ""
echo "BRONZE LAYER:"
docker exec sme-trino trino --execute "SELECT 'twitter_human_bots' as table_name, COUNT(*) as records FROM minio.kol_bronze.twitter_human_bots" 2>/dev/null || echo "  twitter_human_bots: N/A"
docker exec sme-trino trino --execute "SELECT 'short_video_trends' as table_name, COUNT(*) as records FROM minio.kol_bronze.short_video_trends" 2>/dev/null || echo "  short_video_trends: N/A"
docker exec sme-trino trino --execute "SELECT 'wikipedia_backlinko' as table_name, COUNT(*) as records FROM minio.kol_bronze.wikipedia_backlinko" 2>/dev/null || echo "  wikipedia_backlinko: N/A"
docker exec sme-trino trino --execute "SELECT 'youtube_trending' as table_name, COUNT(*) as records FROM minio.kol_bronze.youtube_trending" 2>/dev/null || echo "  youtube_trending: N/A"

# Silver counts
echo ""
echo "SILVER LAYER:"
docker exec sme-trino trino --execute "SELECT 'kol_profiles' as table_name, COUNT(*) as records FROM minio.kol_silver.kol_profiles" 2>/dev/null || echo "  kol_profiles: N/A"
docker exec sme-trino trino --execute "SELECT 'kol_content' as table_name, COUNT(*) as records FROM minio.kol_silver.kol_content" 2>/dev/null || echo "  kol_content: N/A"
docker exec sme-trino trino --execute "SELECT 'kol_trust_features' as table_name, COUNT(*) as records FROM minio.kol_silver.kol_trust_features" 2>/dev/null || echo "  kol_trust_features: N/A"
docker exec sme-trino trino --execute "SELECT 'kol_engagement_metrics' as table_name, COUNT(*) as records FROM minio.kol_silver.kol_engagement_metrics" 2>/dev/null || echo "  kol_engagement_metrics: N/A"

# Gold counts
echo ""
echo "GOLD LAYER:"
docker exec sme-trino trino --execute "SELECT 'dim_kol' as table_name, COUNT(*) as records FROM minio.kol_gold.dim_kol" 2>/dev/null || echo "  dim_kol: N/A"
docker exec sme-trino trino --execute "SELECT 'ml_trust_features_engineered' as table_name, COUNT(*) as records FROM minio.kol_gold.ml_trust_features_engineered" 2>/dev/null || echo "  ml_trust_features_engineered: N/A"

echo ""
echo "=============================================="
echo "✅ Setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Query data:    docker exec -it sme-trino trino"
echo "  2. Run ETL:       make bronze-to-silver"
echo "  3. Train models:  docker exec kol-trainer python -m models.trust.train_xgb"

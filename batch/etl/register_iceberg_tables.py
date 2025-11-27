#!/usr/bin/env python3
"""
Register Data Tables to Iceberg Catalog via Spark
=================================================
Script này đọc data từ MinIO (JSONL) và register vào Iceberg catalog
để Trino có thể query được.

Chạy trên Spark Cluster:
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.apache.hadoop:hadoop-aws:3.3.4 \
    /opt/batch/etl/register_iceberg_tables.py
"""

import argparse
import sys
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *


# ============================================================================
# CONFIGURATION
# ============================================================================
MINIO_ENDPOINT = "http://sme-minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin123"

BUCKET = "kol-platform"
S3A_BASE = f"s3a://{BUCKET}"


def create_spark_session():
    """Create Spark session with S3A and Iceberg support"""
    return (SparkSession.builder
        .appName("KOL-RegisterIcebergTables")
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.sql.catalogImplementation", "hive")
        .config("spark.sql.warehouse.dir", f"{S3A_BASE}/warehouse")
        .getOrCreate())


def register_bronze_tables(spark, dry_run=False):
    """Register Bronze layer tables as Parquet in catalog"""
    print("\n" + "="*60)
    print("REGISTERING BRONZE TABLES")
    print("="*60)
    
    bronze_sources = [
        "short_video_trends",
        "twitter_human_bots", 
        "wikipedia_backlinko",
        "youtube_trending"
    ]
    
    for source in bronze_sources:
        try:
            source_path = f"{S3A_BASE}/bronze/raw/{source}/"
            print(f"\n📂 Processing: {source}")
            print(f"   Path: {source_path}")
            
            # Read JSONL files
            df = spark.read.json(source_path)
            
            if df.count() == 0:
                print(f"   ⚠️ No data found")
                continue
                
            record_count = df.count()
            print(f"   ✅ Found {record_count:,} records")
            print(f"   Schema: {df.columns}")
            
            # Add partition column if not exists
            if "dt" not in df.columns:
                df = df.withColumn("dt", F.current_date())
            
            # Target path for Parquet
            parquet_path = f"{S3A_BASE}/bronze/tables/{source}/"
            
            if dry_run:
                print(f"   [DRY-RUN] Would write to: {parquet_path}")
                df.show(2, truncate=50)
            else:
                # Write as Parquet with partitioning
                (df.write
                    .mode("overwrite")
                    .partitionBy("dt")
                    .parquet(parquet_path))
                print(f"   ✅ Written to: {parquet_path}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")


def register_silver_tables(spark, dry_run=False):
    """Register Silver layer tables as Parquet"""
    print("\n" + "="*60)
    print("REGISTERING SILVER TABLES")
    print("="*60)
    
    silver_tables = [
        "kol_profiles",
        "kol_content",
        "kol_trust_features",
        "kol_engagement_metrics"
    ]
    
    for table in silver_tables:
        try:
            source_path = f"{S3A_BASE}/silver/{table}/"
            print(f"\n📂 Processing: {table}")
            print(f"   Path: {source_path}")
            
            # Read JSONL files
            df = spark.read.json(source_path)
            
            if df.count() == 0:
                print(f"   ⚠️ No data found")
                continue
                
            record_count = df.count()
            print(f"   ✅ Found {record_count:,} records")
            
            # Add partition column if not exists  
            if "dt" not in df.columns:
                df = df.withColumn("dt", F.current_date())
            
            # Target path for Parquet
            parquet_path = f"{S3A_BASE}/silver/parquet/{table}/"
            
            if dry_run:
                print(f"   [DRY-RUN] Would write to: {parquet_path}")
                df.printSchema()
            else:
                # Write as Parquet
                (df.write
                    .mode("overwrite")
                    .partitionBy("dt")
                    .parquet(parquet_path))
                print(f"   ✅ Written to: {parquet_path}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")


def register_gold_tables(spark, dry_run=False):
    """Register Gold layer tables as Parquet"""
    print("\n" + "="*60)
    print("REGISTERING GOLD TABLES")
    print("="*60)
    
    gold_tables = [
        "dim_kol",
        "dim_platform",
        "dim_time",
        "dim_content_type",
        "fact_kol_performance",
        "ml_trust_training",
        "agg_platform_kpi"
    ]
    
    for table in gold_tables:
        try:
            source_path = f"{S3A_BASE}/gold/{table}/"
            print(f"\n📂 Processing: {table}")
            print(f"   Path: {source_path}")
            
            # Read JSONL files
            df = spark.read.json(source_path)
            
            if df.count() == 0:
                print(f"   ⚠️ No data found")
                continue
                
            record_count = df.count()
            print(f"   ✅ Found {record_count:,} records")
            
            # Add partition column if not exists
            if "dt" not in df.columns:
                df = df.withColumn("dt", F.current_date())
            
            # Target path for Parquet
            parquet_path = f"{S3A_BASE}/gold/parquet/{table}/"
            
            if dry_run:
                print(f"   [DRY-RUN] Would write to: {parquet_path}")
            else:
                # Write as Parquet
                (df.write
                    .mode("overwrite")
                    .partitionBy("dt")
                    .parquet(parquet_path))
                print(f"   ✅ Written to: {parquet_path}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")


def create_trino_ddl():
    """Generate Trino DDL to create external tables"""
    print("\n" + "="*60)
    print("TRINO DDL - Run these in Trino CLI")
    print("="*60)
    
    ddl = """
-- ============================================================
-- BRONZE TABLES
-- ============================================================
CREATE SCHEMA IF NOT EXISTS minio.kol_bronze WITH (location = 's3a://kol-platform/bronze/');

CREATE TABLE IF NOT EXISTS minio.kol_bronze.short_video_trends (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/bronze/tables/short_video_trends/'
);

CREATE TABLE IF NOT EXISTS minio.kol_bronze.twitter_human_bots (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/bronze/tables/twitter_human_bots/'
);

CREATE TABLE IF NOT EXISTS minio.kol_bronze.wikipedia_backlinko (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/bronze/tables/wikipedia_backlinko/'
);

CREATE TABLE IF NOT EXISTS minio.kol_bronze.youtube_trending (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/bronze/tables/youtube_trending/'
);

-- ============================================================
-- SILVER TABLES
-- ============================================================
CREATE SCHEMA IF NOT EXISTS minio.kol_silver WITH (location = 's3a://kol-platform/silver/');

CREATE TABLE IF NOT EXISTS minio.kol_silver.kol_profiles (
    kol_id VARCHAR,
    platform VARCHAR,
    display_name VARCHAR,
    description VARCHAR,
    profile_url VARCHAR,
    followers_count BIGINT,
    following_count BIGINT,
    total_videos BIGINT,
    profile_source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/parquet/kol_profiles/'
);

CREATE TABLE IF NOT EXISTS minio.kol_silver.kol_content (
    content_id VARCHAR,
    kol_id VARCHAR,
    platform VARCHAR,
    content_type VARCHAR,
    title VARCHAR,
    description VARCHAR,
    publish_date DATE,
    category VARCHAR,
    tags VARCHAR,
    content_source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/parquet/kol_content/'
);

CREATE TABLE IF NOT EXISTS minio.kol_silver.kol_trust_features (
    kol_id VARCHAR,
    platform VARCHAR,
    followers_count BIGINT,
    following_count BIGINT,
    tweet_count BIGINT,
    favorites_count BIGINT,
    listed_count BIGINT,
    verified BOOLEAN,
    default_profile BOOLEAN,
    default_profile_image BOOLEAN,
    has_url BOOLEAN,
    has_description BOOLEAN,
    account_age_days BIGINT,
    followers_following_ratio DOUBLE,
    tweets_per_day DOUBLE,
    is_bot BOOLEAN,
    trust_source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/parquet/kol_trust_features/'
);

CREATE TABLE IF NOT EXISTS minio.kol_silver.kol_engagement_metrics (
    kol_id VARCHAR,
    platform VARCHAR,
    views BIGINT,
    likes BIGINT,
    comments BIGINT,
    shares BIGINT,
    engagement_source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/parquet/kol_engagement_metrics/'
);

-- ============================================================
-- GOLD TABLES
-- ============================================================
CREATE SCHEMA IF NOT EXISTS minio.kol_gold WITH (location = 's3a://kol-platform/gold/');

CREATE TABLE IF NOT EXISTS minio.kol_gold.dim_kol (
    kol_sk BIGINT,
    kol_id VARCHAR,
    platform VARCHAR,
    display_name VARCHAR,
    description VARCHAR,
    profile_url VARCHAR,
    valid_from DATE,
    valid_to DATE,
    is_current BOOLEAN,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/dim_kol/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.dim_platform (
    platform_sk BIGINT,
    platform_code VARCHAR,
    platform_name VARCHAR,
    category VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/dim_platform/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.dim_time (
    time_sk BIGINT,
    full_date DATE,
    year INT,
    quarter INT,
    month INT,
    week INT,
    day_of_week INT,
    day_name VARCHAR,
    is_weekend BOOLEAN,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/dim_time/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.dim_content_type (
    content_type_sk BIGINT,
    content_type_code VARCHAR,
    content_type_name VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/dim_content_type/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.fact_kol_performance (
    perf_sk BIGINT,
    kol_sk BIGINT,
    platform_sk BIGINT,
    time_sk BIGINT,
    content_type_sk BIGINT,
    followers_count BIGINT,
    following_count BIGINT,
    total_videos BIGINT,
    total_views BIGINT,
    total_likes BIGINT,
    total_comments BIGINT,
    total_shares BIGINT,
    engagement_rate DOUBLE,
    is_verified BOOLEAN,
    is_bot BOOLEAN,
    trust_score DOUBLE,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/fact_kol_performance/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.ml_trust_training (
    kol_id VARCHAR,
    platform VARCHAR,
    followers_count BIGINT,
    following_count BIGINT,
    tweet_count BIGINT,
    favorites_count BIGINT,
    listed_count BIGINT,
    verified BOOLEAN,
    default_profile BOOLEAN,
    default_profile_image BOOLEAN,
    has_url BOOLEAN,
    has_description BOOLEAN,
    account_age_days BIGINT,
    followers_following_ratio DOUBLE,
    tweets_per_day DOUBLE,
    is_bot INT,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/ml_trust_training/'
);

CREATE TABLE IF NOT EXISTS minio.kol_gold.agg_platform_kpi (
    platform VARCHAR,
    total_kols BIGINT,
    total_followers BIGINT,
    total_engagement BIGINT,
    avg_engagement_rate DOUBLE,
    verified_ratio DOUBLE,
    bot_ratio DOUBLE,
    report_date DATE,
    dt DATE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/parquet/agg_platform_kpi/'
);

-- Verification queries
SELECT 'kol_bronze.short_video_trends' as tbl, COUNT(*) as cnt FROM minio.kol_bronze.short_video_trends
UNION ALL
SELECT 'kol_bronze.twitter_human_bots', COUNT(*) FROM minio.kol_bronze.twitter_human_bots
UNION ALL
SELECT 'kol_bronze.wikipedia_backlinko', COUNT(*) FROM minio.kol_bronze.wikipedia_backlinko
UNION ALL
SELECT 'kol_bronze.youtube_trending', COUNT(*) FROM minio.kol_bronze.youtube_trending;
"""
    print(ddl)
    return ddl


def main():
    parser = argparse.ArgumentParser(description='Register tables to Iceberg catalog')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--layer', choices=['bronze', 'silver', 'gold', 'all'], 
                       default='all', help='Which layer to process')
    parser.add_argument('--ddl-only', action='store_true', help='Only generate DDL')
    args = parser.parse_args()
    
    if args.ddl_only:
        create_trino_ddl()
        return
    
    print("="*60)
    print("KOL PLATFORM - REGISTER ICEBERG TABLES")
    print("="*60)
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        if args.layer in ['bronze', 'all']:
            register_bronze_tables(spark, args.dry_run)
            
        if args.layer in ['silver', 'all']:
            register_silver_tables(spark, args.dry_run)
            
        if args.layer in ['gold', 'all']:
            register_gold_tables(spark, args.dry_run)
        
        print("\n" + "="*60)
        print("✅ REGISTRATION COMPLETE!")
        print("="*60)
        print("\nNext steps:")
        print("1. Run the DDL in Trino to create external tables:")
        print("   docker exec -it sme-trino trino")
        print("   Then paste the DDL from --ddl-only option")
        print("\n2. Or use this script with --ddl-only to get DDL")
        
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

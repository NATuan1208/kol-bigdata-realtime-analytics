"""
TikTok Bronze to Silver ETL (Idempotent Version)
=================================================

Transform TikTok data from Bronze (Iceberg) to Silver (Parquet) layer.
This script is IDEMPOTENT - can be run multiple times safely.

Strategy:
1. Read existing Silver data, keep non-TikTok records (Twitter, YouTube, etc.)
2. Read Bronze TikTok data, transform to Silver schema
3. Deduplicate by primary key
4. Union and overwrite Silver

Gap 3 Implementation - Part of Lakehouse ETL Pipeline

Usage:
    docker exec kol-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262" \
        /opt/batch/etl/tiktok_bronze_to_silver.py [--dry-run]

Author: KOL Analytics Team
Date: 2025-12-05 (Updated with idempotent logic)
"""

import argparse
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, when, coalesce, current_timestamp, udf
)
from pyspark.sql.types import LongType


def create_spark_session() -> SparkSession:
    """Create Spark session with Iceberg + Hive + S3 configs."""
    
    spark = SparkSession.builder \
        .appName("TikTok-Bronze-to-Silver-ETL-Idempotent") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.kol_lake", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.kol_lake.catalog-impl", "org.apache.iceberg.hive.HiveCatalog") \
        .config("spark.sql.catalog.kol_lake.uri", "thrift://sme-hive-metastore:9083") \
        .config("spark.sql.catalog.kol_lake.warehouse", "s3a://kol-platform/") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://sme-minio:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin123") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.hadoop.hive.metastore.uris", "thrift://sme-hive-metastore:9083") \
        .enableHiveSupport() \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark


def parse_count_string(value: str) -> int:
    """Parse count strings like '1.2M', '36.5K' to integer."""
    if value is None or value == '':
        return 0
    
    value = str(value).strip().upper().replace(',', '')
    
    try:
        if 'M' in value:
            return int(float(value.replace('M', '')) * 1_000_000)
        if 'K' in value:
            return int(float(value.replace('K', '')) * 1_000)
        return int(float(value))
    except (ValueError, TypeError):
        return 0


parse_count_udf = udf(parse_count_string, LongType())


def transform_profiles(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze tiktok_profiles → Silver kol_profiles (IDEMPOTENT).
    
    Logic:
    1. Read Silver kol_profiles, filter OUT TikTok (keep Twitter, etc.)
    2. Read Bronze tiktok_profiles, transform to Silver schema
    3. Deduplicate TikTok by kol_id
    4. Union with non-TikTok data
    5. Overwrite Silver
    """
    
    print("\n" + "=" * 70)
    print("📊 TRANSFORM: tiktok_profiles → kol_profiles (IDEMPOTENT)")
    print("=" * 70)
    
    silver_path = "s3a://kol-platform/silver/kol_profiles/"
    
    result = {
        "table": "kol_profiles",
        "existing_other": 0,
        "new_tiktok": 0,
        "final_count": 0,
        "status": "pending"
    }
    
    try:
        # Step 1: Read existing Silver and keep non-TikTok
        print("\n   📥 Step 1: Reading existing Silver kol_profiles...")
        try:
            existing_df = spark.read.parquet(silver_path)
            non_tiktok_df = existing_df.filter(col("platform") != "tiktok")
            result["existing_other"] = non_tiktok_df.count()
            print(f"      Non-TikTok records to keep: {result['existing_other']:,}")
        except Exception as e:
            print(f"      ⚠️ No existing Silver data or error: {e}")
            non_tiktok_df = None
            result["existing_other"] = 0
        
        # Step 2: Read Bronze and transform
        print("\n   📥 Step 2: Reading Bronze tiktok_profiles...")
        bronze_df = spark.read.format("iceberg").load("kol_lake.kol_bronze.tiktok_profiles")
        bronze_count = bronze_df.count()
        print(f"      Bronze records: {bronze_count}")
        
        if bronze_count == 0:
            print("      ⚠️ No Bronze data to transform")
            result["status"] = "no_data"
            return result
        
        # Transform to Silver schema
        tiktok_silver_df = bronze_df.select(
            col("username").alias("kol_id"),
            lit("tiktok").alias("platform"),
            col("username").alias("username"),
            col("nickname").alias("display_name"),
            col("bio").alias("description"),
            col("profile_url").alias("profile_url"),
            col("avatar_url").alias("profile_image_url"),
            # Cast to int to match existing Twitter schema (0=false, 1=true)
            when(col("verified") == True, 1).otherwise(0).alias("verified"),
            col("event_time").alias("created_at"),
            parse_count_udf(col("followers_raw")).alias("followers_count"),
            parse_count_udf(col("following_raw")).alias("following_count"),
            lit(0).cast("bigint").alias("post_count"),
            lit("tiktok_bronze").alias("_source"),
            current_timestamp().cast("string").alias("_ingested_at")
        )
        
        # Step 3: Deduplicate TikTok by kol_id + platform
        print("\n   🔄 Step 3: Deduplicating TikTok records...")
        tiktok_silver_df = tiktok_silver_df.dropDuplicates(["kol_id", "platform"])
        result["new_tiktok"] = tiktok_silver_df.count()
        print(f"      TikTok records after dedupe: {result['new_tiktok']}")
        
        # Step 4: Union with non-TikTok
        print("\n   🔗 Step 4: Merging with existing non-TikTok data...")
        if non_tiktok_df is not None and result["existing_other"] > 0:
            final_df = non_tiktok_df.unionByName(tiktok_silver_df, allowMissingColumns=True)
        else:
            final_df = tiktok_silver_df
        
        # Final dedupe (safety)
        final_df = final_df.dropDuplicates(["kol_id", "platform"])
        result["final_count"] = final_df.count()
        print(f"      Final record count: {result['final_count']:,}")
        
        # Show sample
        print("\n   📋 Sample TikTok data:")
        tiktok_silver_df.select("kol_id", "platform", "display_name", "followers_count").show(3, truncate=False)
        
        # Show breakdown
        print("\n   📊 Platform breakdown:")
        final_df.groupBy("platform").count().show()
        
        if dry_run:
            print("\n   🔍 DRY RUN - Not writing changes")
            result["status"] = "dry_run"
            return result
        
        # Step 5: Overwrite Silver
        print("\n   💾 Step 5: Writing to Silver (OVERWRITE)...")
        final_df.write \
            .mode("overwrite") \
            .parquet(silver_path)
        
        print(f"   ✅ Written {result['final_count']:,} records to Silver kol_profiles")
        result["status"] = "success"
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def transform_videos(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze tiktok_videos → Silver kol_content (IDEMPOTENT).
    
    Logic:
    1. Read Silver kol_content, filter OUT TikTok (keep YouTube, etc.)
    2. Read Bronze tiktok_videos, transform to Silver schema
    3. Deduplicate TikTok by content_id
    4. Union with non-TikTok data
    5. Overwrite Silver
    """
    
    print("\n" + "=" * 70)
    print("📊 TRANSFORM: tiktok_videos → kol_content (IDEMPOTENT)")
    print("=" * 70)
    
    silver_path = "s3a://kol-platform/silver/kol_content/"
    
    result = {
        "table": "kol_content",
        "existing_other": 0,
        "new_tiktok": 0,
        "final_count": 0,
        "status": "pending"
    }
    
    try:
        # Step 1: Read existing Silver and keep non-TikTok
        print("\n   📥 Step 1: Reading existing Silver kol_content...")
        try:
            existing_df = spark.read.parquet(silver_path)
            non_tiktok_df = existing_df.filter(col("platform") != "tiktok")
            result["existing_other"] = non_tiktok_df.count()
            print(f"      Non-TikTok records to keep: {result['existing_other']:,}")
        except Exception as e:
            print(f"      ⚠️ No existing Silver data or error: {e}")
            non_tiktok_df = None
            result["existing_other"] = 0
        
        # Step 2: Read Bronze and transform
        print("\n   📥 Step 2: Reading Bronze tiktok_videos...")
        bronze_df = spark.read.format("iceberg").load("kol_lake.kol_bronze.tiktok_videos")
        bronze_count = bronze_df.count()
        print(f"      Bronze records: {bronze_count}")
        
        if bronze_count == 0:
            print("      ⚠️ No Bronze data to transform")
            result["status"] = "no_data"
            return result
        
        # Transform to Silver schema
        tiktok_silver_df = bronze_df.select(
            col("video_id").alias("content_id"),
            col("username").alias("kol_id"),
            lit("tiktok").alias("platform"),
            lit("video").alias("content_type"),
            when(col("caption").isNotNull(), 
                 col("caption").substr(1, 100)).otherwise(lit("")).alias("title"),
            coalesce(col("caption"), lit("")).alias("description"),
            col("video_url").alias("url"),
            col("event_time").alias("published_at"),
            coalesce(col("view_count"), lit(0)).alias("views"),
            coalesce(col("like_count"), lit(0)).alias("likes"),
            coalesce(col("comment_count"), lit(0)).alias("comments"),
            coalesce(col("share_count"), lit(0)).alias("shares"),
            lit("tiktok_bronze").alias("_source"),
            current_timestamp().cast("string").alias("_ingested_at")
        )
        
        # Step 3: Deduplicate TikTok by content_id + platform
        print("\n   🔄 Step 3: Deduplicating TikTok records...")
        tiktok_silver_df = tiktok_silver_df.dropDuplicates(["content_id", "platform"])
        result["new_tiktok"] = tiktok_silver_df.count()
        print(f"      TikTok records after dedupe: {result['new_tiktok']}")
        
        # Step 4: Union with non-TikTok
        print("\n   🔗 Step 4: Merging with existing non-TikTok data...")
        if non_tiktok_df is not None and result["existing_other"] > 0:
            final_df = non_tiktok_df.unionByName(tiktok_silver_df, allowMissingColumns=True)
        else:
            final_df = tiktok_silver_df
        
        # Final dedupe (safety)
        final_df = final_df.dropDuplicates(["content_id", "platform"])
        result["final_count"] = final_df.count()
        print(f"      Final record count: {result['final_count']:,}")
        
        # Show sample
        print("\n   📋 Sample TikTok data:")
        tiktok_silver_df.select("content_id", "kol_id", "platform", "views", "likes").show(3, truncate=False)
        
        # Show breakdown
        print("\n   📊 Platform breakdown:")
        final_df.groupBy("platform").count().show()
        
        if dry_run:
            print("\n   🔍 DRY RUN - Not writing changes")
            result["status"] = "dry_run"
            return result
        
        # Step 5: Overwrite Silver
        print("\n   💾 Step 5: Writing to Silver (OVERWRITE)...")
        final_df.write \
            .mode("overwrite") \
            .parquet(silver_path)
        
        print(f"   ✅ Written {result['final_count']:,} records to Silver kol_content")
        result["status"] = "success"
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def verify_results(spark: SparkSession):
    """Verify the transformation results."""
    
    print("\n" + "=" * 70)
    print("🔍 VERIFICATION")
    print("=" * 70)
    
    try:
        # kol_profiles
        profiles_df = spark.read.parquet("s3a://kol-platform/silver/kol_profiles/")
        print("\n   📊 Silver kol_profiles:")
        profiles_df.groupBy("platform").count().orderBy("platform").show()
        
        # Check for duplicates
        total = profiles_df.count()
        unique = profiles_df.dropDuplicates(["kol_id", "platform"]).count()
        if total != unique:
            print(f"   ⚠️ WARNING: Found {total - unique} duplicates!")
        else:
            print(f"   ✅ No duplicates found (total: {total:,})")
        
    except Exception as e:
        print(f"   ⚠️ Cannot read kol_profiles: {e}")
    
    try:
        # kol_content
        content_df = spark.read.parquet("s3a://kol-platform/silver/kol_content/")
        print("\n   📊 Silver kol_content:")
        content_df.groupBy("platform").count().orderBy("platform").show()
        
        # Check for duplicates
        total = content_df.count()
        unique = content_df.dropDuplicates(["content_id", "platform"]).count()
        if total != unique:
            print(f"   ⚠️ WARNING: Found {total - unique} duplicates!")
        else:
            print(f"   ✅ No duplicates found (total: {total:,})")
        
    except Exception as e:
        print(f"   ⚠️ Cannot read kol_content: {e}")


def main():
    parser = argparse.ArgumentParser(description="TikTok Bronze to Silver ETL (Idempotent)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    parser.add_argument("--profiles-only", action="store_true", help="Only transform profiles")
    parser.add_argument("--videos-only", action="store_true", help="Only transform videos")
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("🚀 TIKTOK BRONZE → SILVER ETL (IDEMPOTENT)")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print("=" * 70)
    
    spark = create_spark_session()
    results = []
    
    # Transform profiles
    if not args.videos_only:
        result = transform_profiles(spark, args.dry_run)
        results.append(result)
    
    # Transform videos
    if not args.profiles_only:
        result = transform_videos(spark, args.dry_run)
        results.append(result)
    
    # Verify if not dry-run
    if not args.dry_run:
        verify_results(spark)
    
    # Summary
    print("\n" + "=" * 70)
    print("📋 SUMMARY")
    print("=" * 70)
    
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "🔍" if r["status"] == "dry_run" else "❌"
        print(f"   {status_icon} {r['table']}: {r.get('final_count', 0):,} records")
        if r.get("existing_other", 0) > 0:
            print(f"      - Existing (non-TikTok): {r['existing_other']:,}")
        print(f"      - New TikTok: {r.get('new_tiktok', 0):,}")
    
    print(f"\n   Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    spark.stop()


if __name__ == "__main__":
    main()

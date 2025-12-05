"""
Add TikTok Profiles to Silver Layer
====================================

Simple script to add deduplicated TikTok profiles from Bronze to Silver.
Uses APPEND mode to add to existing data without reading/modifying it.

Usage:
    docker exec kol-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262" \
        /opt/batch/etl/add_tiktok_profiles.py
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, when, current_timestamp, udf
from pyspark.sql.types import LongType


def create_spark_session() -> SparkSession:
    """Create Spark session with Iceberg + S3 configs."""
    
    spark = SparkSession.builder \
        .appName("Add-TikTok-Profiles-to-Silver") \
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


def main():
    print("\n" + "=" * 60)
    print("🚀 ADD TIKTOK PROFILES TO SILVER")
    print("=" * 60)
    
    spark = create_spark_session()
    silver_path = "s3a://kol-platform/silver/kol_profiles/"
    
    # Read Bronze TikTok profiles
    print("\n📥 Reading Bronze tiktok_profiles...")
    bronze_df = spark.read.format("iceberg").load("kol_lake.kol_bronze.tiktok_profiles")
    bronze_count = bronze_df.count()
    print(f"   Bronze records: {bronze_count}")
    
    # Transform to Silver schema (matching existing Twitter schema)
    print("\n🔄 Transforming to Silver schema...")
    tiktok_df = bronze_df.select(
        col("username").alias("kol_id"),
        lit("tiktok").alias("platform"),
        col("username").alias("username"),
        col("nickname").alias("display_name"),
        col("bio").alias("bio"),
        parse_count_udf(col("followers_raw")).alias("followers_count"),
        parse_count_udf(col("following_raw")).alias("following_count"),
        lit(0).cast("bigint").alias("post_count"),
        # Match Twitter schema: verified as boolean
        col("verified").alias("verified"),
        lit(None).cast("string").alias("account_created_at"),
        col("profile_url").alias("profile_url"),
        lit(None).cast("string").alias("category"),
        lit("tiktok_bronze").alias("source"),
        current_timestamp().cast("string").alias("processed_at")
    )
    
    # Deduplicate
    print("\n🔄 Deduplicating...")
    tiktok_df = tiktok_df.dropDuplicates(["kol_id", "platform"])
    dedupe_count = tiktok_df.count()
    print(f"   After dedupe: {dedupe_count}")
    
    # Show sample
    print("\n📋 Sample data:")
    tiktok_df.select("kol_id", "display_name", "followers_count", "verified").show(5, truncate=False)
    
    # Append to Silver
    print("\n💾 Appending to Silver...")
    tiktok_df.write \
        .mode("append") \
        .parquet(silver_path)
    
    print(f"\n✅ Added {dedupe_count} TikTok profiles to Silver!")
    
    # Verify
    print("\n🔍 Verification:")
    verify_df = spark.read.parquet(silver_path)
    verify_df.groupBy("platform").count().show()
    
    # Check for duplicates
    total = verify_df.count()
    unique = verify_df.dropDuplicates(["kol_id", "platform"]).count()
    if total != unique:
        print(f"   ⚠️ WARNING: {total - unique} duplicates found!")
    else:
        print(f"   ✅ No duplicates (total: {total:,})")
    
    spark.stop()
    print("\n" + "=" * 60)
    print("✅ DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()

"""
Clean Silver TikTok Duplicates
===============================

Remove duplicate TikTok records from Silver layer and re-transform from clean Bronze.

Steps:
1. Read Silver kol_profiles, filter out TikTok records (keep Twitter only)
2. Read clean Bronze tiktok_profiles, transform to Silver schema
3. Deduplicate by (kol_id, platform)
4. Union with Twitter data and overwrite Silver

Usage:
    docker exec kol-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        /opt/batch/etl/clean_silver_tiktok.py [--dry-run]

Author: KOL Analytics Team
Date: 2025-12-05
"""

import argparse
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, lit, when, current_timestamp, udf
)
from pyspark.sql.types import LongType


def create_spark_session() -> SparkSession:
    """Create Spark session with Hive + S3 configs."""
    
    spark = SparkSession.builder \
        .appName("Clean-Silver-TikTok-Duplicates") \
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
    
    value = str(value).strip().upper()
    
    try:
        value = value.replace(',', '')
        if 'M' in value:
            return int(float(value.replace('M', '')) * 1_000_000)
        if 'K' in value:
            return int(float(value.replace('K', '')) * 1_000)
        return int(float(value))
    except (ValueError, TypeError):
        return 0


parse_count_udf = udf(parse_count_string, LongType())


def main():
    parser = argparse.ArgumentParser(description="Clean Silver TikTok duplicates")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("🧹 CLEAN SILVER TIKTOK DUPLICATES")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print("=" * 70)
    
    spark = create_spark_session()
    
    silver_path = "s3a://kol-platform/silver/kol_profiles/"
    # Bronze Iceberg table location (from SHOW CREATE TABLE)
    bronze_path = "s3a://kol-platform/bronze/tiktok_profiles_clean-87dafb8ecc6943b0bd5a3b2d44e9bd5e/"
    
    # Step 1: Read current Silver and keep only Twitter
    print("\n📥 Step 1: Reading Silver kol_profiles...")
    try:
        silver_df = spark.read.parquet(silver_path)
        total_silver = silver_df.count()
        print(f"   Total Silver records: {total_silver:,}")
        
        # Count by platform before
        print("   Records by platform (BEFORE):")
        silver_df.groupBy("platform").count().show()
        
        # Keep only Twitter
        twitter_df = silver_df.filter(col("platform") == "twitter")
        twitter_count = twitter_df.count()
        print(f"   Twitter records to keep: {twitter_count:,}")
        
    except Exception as e:
        print(f"   ❌ Error reading Silver: {e}")
        spark.stop()
        return
    
    # Step 2: Read clean Bronze TikTok and transform
    print("\n📥 Step 2: Reading Bronze tiktok_profiles...")
    try:
        bronze_df = spark.read.parquet(bronze_path)
        bronze_count = bronze_df.count()
        print(f"   Bronze TikTok records: {bronze_count:,}")
        
        # Transform to Silver schema
        tiktok_silver_df = bronze_df.select(
            col("username").alias("kol_id"),
            lit("tiktok").alias("platform"),
            col("username").alias("username"),
            col("nickname").alias("display_name"),
            col("bio").alias("description"),
            col("profile_url").alias("profile_url"),
            col("avatar_url").alias("profile_image_url"),
            when(col("verified") == True, 1).otherwise(0).alias("verified"),
            col("event_time").alias("created_at"),
            parse_count_udf(col("followers_raw")).alias("followers_count"),
            parse_count_udf(col("following_raw")).alias("following_count"),
            lit(0).cast("bigint").alias("post_count"),
            lit("tiktok_bronze_clean").alias("_source"),
            current_timestamp().cast("string").alias("_ingested_at")
        )
        
        # Deduplicate TikTok by kol_id
        tiktok_silver_df = tiktok_silver_df.dropDuplicates(["kol_id", "platform"])
        tiktok_count = tiktok_silver_df.count()
        print(f"   TikTok records after dedupe: {tiktok_count:,}")
        
    except Exception as e:
        print(f"   ❌ Error reading/transforming Bronze: {e}")
        spark.stop()
        return
    
    # Step 3: Union Twitter + TikTok
    print("\n🔄 Step 3: Merging Twitter + TikTok...")
    
    # Ensure same schema
    final_df = twitter_df.unionByName(tiktok_silver_df, allowMissingColumns=True)
    
    # Final deduplicate (safety)
    final_df = final_df.dropDuplicates(["kol_id", "platform"])
    final_count = final_df.count()
    
    print(f"   Final record count: {final_count:,}")
    print("   Records by platform (AFTER):")
    final_df.groupBy("platform").count().show()
    
    # Step 4: Write back
    if args.dry_run:
        print("\n🔍 DRY RUN - Not writing changes")
        print("   Sample of final data:")
        final_df.select("kol_id", "platform", "display_name", "followers_count").show(5)
    else:
        print("\n💾 Step 4: Writing to Silver (overwrite)...")
        try:
            final_df.write \
                .mode("overwrite") \
                .parquet(silver_path)
            
            print(f"   ✅ Successfully written {final_count:,} records")
            
            # Verify
            print("\n🔍 Verification:")
            verify_df = spark.read.parquet(silver_path)
            verify_df.groupBy("platform").count().show()
            
        except Exception as e:
            print(f"   ❌ Error writing: {e}")
    
    print("\n" + "=" * 70)
    print(f"✅ COMPLETED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    spark.stop()


if __name__ == "__main__":
    main()

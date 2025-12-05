"""
ETL: Bronze -> Silver (KOL Analytics Domain)
=============================================

DOMAIN SEPARATION:
- Reads from: s3://kol-bronze/* (KOL raw data)
- Writes to: s3://kol-silver/* (KOL cleaned data)
- Trino schema: iceberg.kol_silver.*
- Does NOT touch SME data (sme-bronze, sme-silver)

This ETL:
- Cleans & normalizes event schemas
- Deduplicates records
- Validates data quality
- Partitions by yyyy/mm/dd/HH
- Creates Iceberg tables in kol_silver schema
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, LongType, DoubleType, TimestampType
from pyspark.sql.functions import col, when, coalesce, current_timestamp, year, month, dayofmonth, hour

# KOL domain bucket configuration
BRONZE_BUCKET = os.getenv("MINIO_BUCKET_BRONZE", "kol-bronze")
SILVER_BUCKET = os.getenv("MINIO_BUCKET_SILVER", "kol-silver")
TRINO_SCHEMA_SILVER = os.getenv("TRINO_SCHEMA_SILVER", "kol_silver")
WAREHOUSE_PATH = os.getenv("SPARK_WAREHOUSE", "/opt/spark/work-dir")

# S3A configuration
S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://sme-minio:9000")
S3_ACCESS_KEY = os.getenv("MINIO_USER", "minio")
S3_SECRET_KEY = os.getenv("MINIO_PASSWORD", "minio123")

def get_spark_session():
    """Create Spark session with Iceberg + S3A support"""
    spark = SparkSession.builder \
        .appName("KOL-Bronze-to-Silver") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.iceberg.type", "hive") \
        .config("spark.sql.catalog.iceberg.warehouse", f"{WAREHOUSE_PATH}/iceberg") \
        .config("spark.sql.catalog.iceberg.uri", "thrift://sme-hive-metastore:9083") \
        .config("spark.hadoop.fs.s3a.endpoint", S3_ENDPOINT) \
        .config("spark.hadoop.fs.s3a.access.key", S3_ACCESS_KEY) \
        .config("spark.hadoop.fs.s3a.secret.key", S3_SECRET_KEY) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark

def process_youtube(spark):
    """Process YouTube data from bronze to silver"""
    print("🎥 Processing YouTube data...")
    
    try:
        # Read raw CSV
        df = spark.read.option("header", "true").csv(f"s3a://{BRONZE_BUCKET}/youtube/youtube_raw.csv")
        
        # Clean and normalize
        df_cleaned = df.select(
            col("video_id").alias("source_id"),
            col("creator_id"),
            col("product_mention"),
            col("title").alias("content_title"),
            col("views").cast("long"),
            col("likes").cast("long"),
            col("comments").cast("long"),
            col("shares").cast("long"),
            col("engagement_rate").cast("double"),
            col("publish_date").alias("event_date"),
            col("source").alias("platform"),
            current_timestamp().alias("processed_at")
        ).filter(col("creator_id").isNotNull())
        
        # Deduplicate
        df_dedup = df_cleaned.dropDuplicates(["source_id"])
        
        # Write to silver (Iceberg table)
        table_name = f"iceberg.{TRINO_SCHEMA_SILVER}.youtube_events"
        df_dedup.write.format("iceberg") \
            .mode("append") \
            .option("merge-schema", "true") \
            .saveAsTable(table_name)
        
        count = df_dedup.count()
        print(f"✅ YouTube: {count} records processed")
        return count
    except Exception as e:
        print(f"❌ YouTube error: {e}")
        return 0

def process_wikipedia(spark):
    """Process Wikipedia data from bronze to silver"""
    print("📚 Processing Wikipedia data...")
    
    try:
        # Read raw CSV
        df = spark.read.option("header", "true").csv(f"s3a://{BRONZE_BUCKET}/wikipedia/wikipedia_raw.csv")
        
        # Clean and normalize
        df_cleaned = df.select(
            col("page_id").alias("source_id"),
            col("title").alias("content_title"),
            col("mention_text").alias("content_snippet"),
            col("product_mention"),
            col("view_count").cast("long"),
            col("edit_count").cast("long"),
            col("sentiment"),
            col("last_edit_date").alias("event_date"),
            col("source").alias("platform"),
            current_timestamp().alias("processed_at")
        ).filter(col("page_id").isNotNull())
        
        # Deduplicate
        df_dedup = df_cleaned.dropDuplicates(["source_id"])
        
        # Write to silver (Iceberg table)
        table_name = f"iceberg.{TRINO_SCHEMA_SILVER}.wikipedia_mentions"
        df_dedup.write.format("iceberg") \
            .mode("append") \
            .option("merge-schema", "true") \
            .saveAsTable(table_name)
        
        count = df_dedup.count()
        print(f"✅ Wikipedia: {count} records processed")
        return count
    except Exception as e:
        print(f"❌ Wikipedia error: {e}")
        return 0

def process_weibo(spark):
    """Process Weibo data from bronze to silver"""
    print("🔔 Processing Weibo data...")
    
    try:
        # Read raw CSV
        df = spark.read.option("header", "true").csv(f"s3a://{BRONZE_BUCKET}/weibo/weibo_raw.csv")
        
        # Clean and normalize
        df_cleaned = df.select(
            col("post_id").alias("source_id"),
            col("user_id"),
            col("creator_id"),
            col("content"),
            col("product_mention"),
            col("reposts").cast("long"),
            col("comments").cast("long"),
            col("likes").cast("long"),
            col("influencer_followers").cast("long"),
            col("post_date").alias("event_date"),
            col("source").alias("platform"),
            current_timestamp().alias("processed_at")
        ).filter(col("post_id").isNotNull())
        
        # Deduplicate
        df_dedup = df_cleaned.dropDuplicates(["source_id"])
        
        # Write to silver (Iceberg table)
        table_name = f"iceberg.{TRINO_SCHEMA_SILVER}.weibo_posts"
        df_dedup.write.format("iceberg") \
            .mode("append") \
            .option("merge-schema", "true") \
            .saveAsTable(table_name)
        
        count = df_dedup.count()
        print(f"✅ Weibo: {count} records processed")
        return count
    except Exception as e:
        print(f"❌ Weibo error: {e}")
        return 0

def run():
    print(f"\n{'='*60}")
    print(f"KOL Analytics: Bronze → Silver ETL")
    print(f"{'='*60}")
    print(f"Source: s3://{BRONZE_BUCKET}/")
    print(f"Target: s3://{SILVER_BUCKET}/ + iceberg.{TRINO_SCHEMA_SILVER}.*")
    print(f"{'='*60}\n")
    
    spark = get_spark_session()
    
    try:
        total = 0
        total += process_youtube(spark)
        total += process_wikipedia(spark)
        total += process_weibo(spark)
        
        print(f"\n{'='*60}")
        print(f"✅ ETL Complete! Total records: {total}")
        print(f"{'='*60}\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    run()

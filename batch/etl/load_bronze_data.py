"""
Bronze Data Loader - Load JSONL from MinIO to Iceberg Tables
==============================================================

Reads JSONL files from MinIO Bronze raw layer and loads them into
Iceberg tables in kol_bronze schema.

Usage:
    spark-submit batch/etl/load_bronze_youtube.py --date 2025-11-16
    spark-submit batch/etl/load_bronze_youtube.py --date 2025-11-16 --source youtube_trending
"""

import sys
import json
import argparse
from datetime import datetime, date
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, lit, to_timestamp
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, DateType

# Canonical Bronze schema (matches JSONL format)
BRONZE_SCHEMA = StructType([
    StructField("kol_id", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("source", StringType(), True),
    StructField("payload", StringType(), True),  # JSON as string
    StructField("ingest_ts", StringType(), True)
])


def create_spark_session(app_name: str = "Bronze Loader") -> SparkSession:
    """
    Create Spark session with Iceberg and S3 configs.
    
    Architecture:
    - Iceberg: HiveCatalog backend (shared metastore with Trino)
    - S3: MinIO with S3A connector
    - Catalog: kol_lake
    - Warehouse: s3a://kol-platform/
    """
    spark = SparkSession.builder \
        .appName(app_name) \
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
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.sql.files.maxPartitionBytes", "134217728") \
        .config("spark.sql.adaptive.enabled", "true") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark


def load_youtube_trending(spark: SparkSession, ingest_date: str):
    """
    Load YouTube trending data from JSONL to Iceberg table.
    
    Args:
        spark: SparkSession
        ingest_date: Date string (YYYY-MM-DD)
    """
    source = "youtube_trending"
    table_name = "kol_lake.kol_bronze.raw_youtube_trending"
    
    # S3 path pattern
    s3_path = f"s3a://kol-platform/bronze/raw/{source}/dt={ingest_date}/*.jsonl"
    
    print(f"=" * 70)
    print(f"📥 LOADING: {source}")
    print(f"   Source: {s3_path}")
    print(f"   Target: {table_name}")
    print(f"=" * 70)
    
    try:
        # Read JSONL files
        df = spark.read \
            .schema(BRONZE_SCHEMA) \
            .json(s3_path)
        
        # Convert ingest_ts to proper timestamp
        df = df.withColumn("ingest_ts", to_timestamp(col("ingest_ts")))
        
        # Add partition column
        df = df.withColumn("dt", lit(ingest_date).cast(DateType()))
        
        # Show sample
        print(f"\n📊 Sample records:")
        df.select("kol_id", "platform", "source", "ingest_ts").show(5, truncate=False)
        
        record_count = df.count()
        print(f"\n✅ Found {record_count} records")
        
        if record_count == 0:
            print(f"⚠️  No data found at {s3_path}")
            return
        
        # Write to Iceberg table (append mode)
        print(f"\n📤 Writing to Iceberg table...")
        df.writeTo(table_name) \
            .using("iceberg") \
            .partitionedBy("dt") \
            .append()
        
        print(f"✅ Successfully loaded {record_count} records into {table_name}")
        
    except Exception as e:
        print(f"❌ Error loading {source}: {e}")
        raise


def load_wikipedia_backlinko(spark: SparkSession, ingest_date: str):
    """
    Load Wikipedia KOL rankings from JSONL to Iceberg table.
    
    Args:
        spark: SparkSession
        ingest_date: Date string (YYYY-MM-DD)
    """
    source = "wikipedia_backlinko"
    table_name = "kol_lake.kol_bronze.raw_wikipedia_backlinko"
    
    s3_path = f"s3a://kol-platform/bronze/raw/{source}/dt={ingest_date}/*.jsonl"
    
    print(f"=" * 70)
    print(f"📥 LOADING: {source}")
    print(f"   Source: {s3_path}")
    print(f"   Target: {table_name}")
    print(f"=" * 70)
    
    try:
        df = spark.read \
            .schema(BRONZE_SCHEMA) \
            .json(s3_path)
        
        df = df.withColumn("ingest_ts", to_timestamp(col("ingest_ts")))
        df = df.withColumn("dt", lit(ingest_date).cast(DateType()))
        
        print(f"\n📊 Sample records:")
        df.select("kol_id", "platform", "source", "ingest_ts").show(5, truncate=False)
        
        record_count = df.count()
        print(f"\n✅ Found {record_count} records")
        
        if record_count == 0:
            print(f"⚠️  No data found at {s3_path}")
            return
        
        print(f"\n📤 Writing to Iceberg table...")
        df.writeTo(table_name) \
            .using("iceberg") \
            .partitionedBy("dt") \
            .append()
        
        print(f"✅ Successfully loaded {record_count} records into {table_name}")
        
    except Exception as e:
        print(f"❌ Error loading {source}: {e}")
        raise


def load_weibo_dataset(spark: SparkSession, ingest_date: str):
    """
    Load Weibo posts from JSONL to Iceberg table.
    
    Args:
        spark: SparkSession
        ingest_date: Date string (YYYY-MM-DD)
    """
    source = "weibo_dataset"
    table_name = "kol_lake.kol_bronze.raw_weibo_dataset"
    
    s3_path = f"s3a://kol-platform/bronze/raw/{source}/dt={ingest_date}/*.jsonl"
    
    print(f"=" * 70)
    print(f"📥 LOADING: {source}")
    print(f"   Source: {s3_path}")
    print(f"   Target: {table_name}")
    print(f"=" * 70)
    
    try:
        df = spark.read \
            .schema(BRONZE_SCHEMA) \
            .json(s3_path)
        
        df = df.withColumn("ingest_ts", to_timestamp(col("ingest_ts")))
        df = df.withColumn("dt", lit(ingest_date).cast(DateType()))
        
        print(f"\n📊 Sample records:")
        df.select("kol_id", "platform", "source", "ingest_ts").show(5, truncate=False)
        
        record_count = df.count()
        print(f"\n✅ Found {record_count} records")
        
        if record_count == 0:
            print(f"⚠️  No data found at {s3_path}")
            return
        
        print(f"\n📤 Writing to Iceberg table...")
        df.writeTo(table_name) \
            .using("iceberg") \
            .partitionedBy("dt") \
            .append()
        
        print(f"✅ Successfully loaded {record_count} records into {table_name}")
        
    except Exception as e:
        print(f"❌ Error loading {source}: {e}")
        raise


def load_all_sources(spark: SparkSession, ingest_date: str):
    """Load all Bronze sources for given date."""
    print("\n" + "=" * 70)
    print(f"🚀 LOADING ALL BRONZE SOURCES FOR {ingest_date}")
    print("=" * 70)
    
    sources = [
        ("youtube_trending", load_youtube_trending),
        ("wikipedia_backlinko", load_wikipedia_backlinko),
        ("weibo_dataset", load_weibo_dataset)
    ]
    
    results = {}
    
    for source_name, load_func in sources:
        try:
            load_func(spark, ingest_date)
            results[source_name] = "✅ Success"
        except Exception as e:
            results[source_name] = f"❌ Failed: {e}"
            print(f"\n⚠️  Continuing with next source...")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 LOAD SUMMARY")
    print("=" * 70)
    for source, status in results.items():
        print(f"   {source}: {status}")
    print("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Load JSONL data from MinIO to Iceberg Bronze tables'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        default=datetime.now().strftime('%Y-%m-%d'),
        help='Ingestion date (YYYY-MM-DD). Default: today'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        choices=['youtube_trending', 'wikipedia_backlinko', 'weibo_dataset', 'all'],
        default='all',
        help='Which source to load. Default: all'
    )
    
    args = parser.parse_args()
    
    # Validate date format
    try:
        datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        print(f"❌ Invalid date format: {args.date}. Use YYYY-MM-DD")
        sys.exit(1)
    
    # Create Spark session
    spark = create_spark_session("KOL Bronze Loader")
    
    print(f"\n⚙️  Configuration:")
    print(f"   Date: {args.date}")
    print(f"   Source: {args.source}")
    print(f"   Catalog: kol_lake")
    print(f"   Schema: kol_bronze")
    
    # Load data
    start_time = datetime.now()
    
    try:
        if args.source == 'all':
            load_all_sources(spark, args.date)
        elif args.source == 'youtube_trending':
            load_youtube_trending(spark, args.date)
        elif args.source == 'wikipedia_backlinko':
            load_wikipedia_backlinko(spark, args.date)
        elif args.source == 'weibo_dataset':
            load_weibo_dataset(spark, args.date)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n⏱️  Total execution time: {elapsed:.2f} seconds")
        print(f"\n✅ Bronze data loading complete!")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        spark.stop()


if __name__ == '__main__':
    main()

"""
KOL Kafka to Iceberg - Simplified Version (No Hive Metastore needed)
=====================================================================

Uses Iceberg Hadoop catalog to write directly to MinIO.
This is simpler than using Hive Metastore.

Flow: Kafka (Redpanda) → Spark Streaming → MinIO (Iceberg Parquet)
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, current_timestamp, lit, 
    to_timestamp, coalesce, when
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    LongType, BooleanType, FloatType
)

# ============================================================================
# CONFIGURATION
# ============================================================================

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://sme-minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")

# Iceberg warehouse on MinIO
ICEBERG_WAREHOUSE = "s3a://kol-bronze/iceberg"
CHECKPOINT_BASE = "/opt/spark/checkpoints/kol"


# ============================================================================
# SCHEMAS
# ============================================================================

DISCOVERY_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("username", StringType(), False),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("caption", StringType(), True),
    StructField("source", StringType(), True),
    StructField("keyword", StringType(), True),
    StructField("niche_hint", StringType(), True),
])

PROFILE_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("username", StringType(), False),
    StructField("nickname", StringType(), True),
    StructField("followers_raw", StringType(), True),
    StructField("following_raw", StringType(), True),
    StructField("likes_raw", StringType(), True),
    StructField("bio", StringType(), True),
    StructField("avatar_url", StringType(), True),
    StructField("verified", BooleanType(), True),
    StructField("profile_url", StringType(), True),
])

VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("video_id", StringType(), False),
    StructField("video_url", StringType(), False),
    StructField("username", StringType(), False),
    StructField("caption", StringType(), True),
    StructField("view_count_raw", StringType(), True),
    StructField("like_count_raw", StringType(), True),
    StructField("comment_count_raw", StringType(), True),
    StructField("share_count_raw", StringType(), True),
    StructField("view_count", IntegerType(), True),
    StructField("like_count", IntegerType(), True),
    StructField("comment_count", IntegerType(), True),
    StructField("share_count", IntegerType(), True),
])

COMMENT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("video_id", StringType(), False),
    StructField("video_url", StringType(), False),
    StructField("username", StringType(), False),
    StructField("comment_text", StringType(), False),
])

PRODUCT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("username", StringType(), False),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("video_views", IntegerType(), True),
    StructField("video_likes", IntegerType(), True),
    StructField("video_comments", IntegerType(), True),
    StructField("video_shares", IntegerType(), True),
    StructField("product_id", StringType(), True),
    StructField("product_title", StringType(), True),
    StructField("seller_id", StringType(), True),
    StructField("price", IntegerType(), True),
    StructField("currency", StringType(), True),
    StructField("product_url", StringType(), True),
    StructField("keyword", StringType(), True),
    StructField("sold_count", IntegerType(), True),
    StructField("sold_count_raw", StringType(), True),
    StructField("sold_delta", IntegerType(), True),
    StructField("engagement_total", IntegerType(), True),
    StructField("engagement_rate", FloatType(), True),
    StructField("est_clicks", IntegerType(), True),
    StructField("est_ctr", FloatType(), True),
])


# ============================================================================
# SPARK SESSION - Using Hadoop Catalog (no Hive Metastore needed)
# ============================================================================

def create_spark_session():
    """Create Spark session with Iceberg Hadoop catalog"""
    
    spark = SparkSession.builder \
        .appName("KOL-Kafka-to-Iceberg-Simple") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.kol", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.kol.type", "hadoop") \
        .config("spark.sql.catalog.kol.warehouse", ICEBERG_WAREHOUSE) \
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT) \
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY) \
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark


# ============================================================================
# CREATE ICEBERG TABLES
# ============================================================================

def create_tables(spark):
    """Create Iceberg tables if not exist"""
    
    print("📦 Creating Iceberg tables...")
    
    # Create namespace
    spark.sql("CREATE NAMESPACE IF NOT EXISTS kol.bronze")
    
    # Discovery table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS kol.bronze.discovery (
            event_id STRING,
            event_timestamp TIMESTAMP,
            event_type STRING,
            platform STRING,
            username STRING,
            video_id STRING,
            video_url STRING,
            caption STRING,
            source STRING,
            keyword STRING,
            niche_hint STRING,
            kafka_key STRING,
            kafka_timestamp TIMESTAMP,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)
    print("   ✅ kol.bronze.discovery")
    
    # Profiles table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS kol.bronze.profiles (
            event_id STRING,
            event_timestamp TIMESTAMP,
            event_type STRING,
            platform STRING,
            username STRING,
            nickname STRING,
            followers_raw STRING,
            following_raw STRING,
            likes_raw STRING,
            bio STRING,
            avatar_url STRING,
            verified BOOLEAN,
            profile_url STRING,
            kafka_key STRING,
            kafka_timestamp TIMESTAMP,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)
    print("   ✅ kol.bronze.profiles")
    
    # Videos table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS kol.bronze.videos (
            event_id STRING,
            event_timestamp TIMESTAMP,
            event_type STRING,
            platform STRING,
            video_id STRING,
            video_url STRING,
            username STRING,
            caption STRING,
            view_count_raw STRING,
            like_count_raw STRING,
            comment_count_raw STRING,
            share_count_raw STRING,
            view_count INT,
            like_count INT,
            comment_count INT,
            share_count INT,
            kafka_key STRING,
            kafka_timestamp TIMESTAMP,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)
    print("   ✅ kol.bronze.videos")
    
    # Comments table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS kol.bronze.comments (
            event_id STRING,
            event_timestamp TIMESTAMP,
            event_type STRING,
            platform STRING,
            video_id STRING,
            video_url STRING,
            username STRING,
            comment_text STRING,
            kafka_key STRING,
            kafka_timestamp TIMESTAMP,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)
    print("   ✅ kol.bronze.comments")
    
    # Products table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS kol.bronze.products (
            event_id STRING,
            event_timestamp TIMESTAMP,
            event_type STRING,
            platform STRING,
            username STRING,
            video_id STRING,
            video_url STRING,
            video_views INT,
            video_likes INT,
            video_comments INT,
            video_shares INT,
            product_id STRING,
            product_title STRING,
            seller_id STRING,
            price INT,
            currency STRING,
            product_url STRING,
            keyword STRING,
            sold_count INT,
            sold_count_raw STRING,
            sold_delta INT,
            engagement_total INT,
            engagement_rate FLOAT,
            est_clicks INT,
            est_ctr FLOAT,
            kafka_key STRING,
            kafka_timestamp TIMESTAMP,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)
    print("   ✅ kol.bronze.products")


# ============================================================================
# BATCH LOAD (simpler than streaming for initial load)
# ============================================================================

def batch_load_topic(spark, topic: str, schema, table_name: str):
    """Batch load all data from Kafka topic to Iceberg table"""
    
    print(f"\n📥 Loading {topic} → kol.bronze.{table_name}")
    
    # Read all data from Kafka (batch mode)
    df = spark.read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()
    
    count = df.count()
    print(f"   📊 Found {count} messages in Kafka")
    
    if count == 0:
        print(f"   ⏭️ No data to load")
        return
    
    # Parse JSON
    parsed = df \
        .select(
            col("key").cast("string").alias("kafka_key"),
            col("timestamp").alias("kafka_timestamp"),
            from_json(col("value").cast("string"), schema).alias("data")
        ) \
        .select(
            "kafka_key",
            "kafka_timestamp",
            "data.*"
        ) \
        .withColumn("ingested_at", current_timestamp()) \
        .withColumn("event_timestamp", to_timestamp(col("event_time"))) \
        .drop("event_time")
    
    # Write to Iceberg
    parsed.writeTo(f"kol.bronze.{table_name}").append()
    
    print(f"   ✅ Loaded {count} records to kol.bronze.{table_name}")


def main():
    print("="*60)
    print("🚀 KOL KAFKA → SPARK → ICEBERG (MinIO)")
    print("="*60)
    print(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"MinIO: {MINIO_ENDPOINT}")
    print(f"Warehouse: {ICEBERG_WAREHOUSE}")
    print("="*60)
    
    # Create Spark session
    spark = create_spark_session()
    print("✅ Spark session created")
    
    # Create tables
    create_tables(spark)
    
    # Batch load all topics
    topics = [
        ("kol.discovery.raw", DISCOVERY_SCHEMA, "discovery"),
        ("kol.profiles.raw", PROFILE_SCHEMA, "profiles"),
        ("kol.videos.raw", VIDEO_SCHEMA, "videos"),
        ("kol.comments.raw", COMMENT_SCHEMA, "comments"),
        ("kol.products.raw", PRODUCT_SCHEMA, "products"),
    ]
    
    for topic, schema, table in topics:
        try:
            batch_load_topic(spark, topic, schema, table)
        except Exception as e:
            print(f"   ❌ Error loading {topic}: {e}")
    
    # Show summary
    print("\n" + "="*60)
    print("📊 ICEBERG TABLES SUMMARY")
    print("="*60)
    
    for _, _, table in topics:
        try:
            count = spark.sql(f"SELECT COUNT(*) FROM kol.bronze.{table}").collect()[0][0]
            print(f"   kol.bronze.{table}: {count} rows")
        except Exception as e:
            print(f"   kol.bronze.{table}: Error - {e}")
    
    print("="*60)
    print("✅ Done!")
    
    spark.stop()


if __name__ == "__main__":
    main()

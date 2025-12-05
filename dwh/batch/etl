"""
Kafka to Bronze Iceberg - TikTok Data ETL
==========================================

Load TikTok data from Kafka topics to Bronze Iceberg tables.

Topics:
    - kol.profiles.raw → kol_bronze.tiktok_profiles
    - kol.videos.raw → kol_bronze.tiktok_videos  
    - kol.comments.raw → kol_bronze.tiktok_comments
    - kol.products.raw → kol_bronze.tiktok_products
    - kol.discovery.raw → kol_bronze.tiktok_discovery

Usage:
    docker exec kol-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3 \
        /opt/batch/etl/kafka_to_bronze_tiktok.py --topic all
"""

import argparse
import json
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, lit, current_timestamp, to_date, 
    coalesce, when, regexp_replace, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, 
    DoubleType, BooleanType, TimestampType
)


# ============================================================================
# KAFKA SCHEMAS - Match exact structure from Kafka topics
# ============================================================================

PROFILE_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
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
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("username", StringType(), True),
    StructField("caption", StringType(), True),
    StructField("view_count_raw", StringType(), True),
    StructField("like_count_raw", StringType(), True),
    StructField("comment_count_raw", StringType(), True),
    StructField("share_count_raw", StringType(), True),
    StructField("view_count", LongType(), True),
    StructField("like_count", LongType(), True),
    StructField("comment_count", LongType(), True),
    StructField("share_count", LongType(), True),
])

COMMENT_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("username", StringType(), True),
    StructField("comment_text", StringType(), True),
])

PRODUCT_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("video_views", LongType(), True),
    StructField("video_likes", LongType(), True),
    StructField("video_comments", LongType(), True),
    StructField("video_shares", LongType(), True),
    StructField("product_id", StringType(), True),
    StructField("product_title", StringType(), True),
    StructField("seller_id", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("currency", StringType(), True),
    StructField("product_url", StringType(), True),
    StructField("keyword", StringType(), True),
    StructField("sold_count", LongType(), True),
    StructField("sold_count_raw", StringType(), True),
    StructField("sold_delta", LongType(), True),
    StructField("engagement_total", LongType(), True),
    StructField("engagement_rate", DoubleType(), True),
    StructField("est_clicks", LongType(), True),
    StructField("est_ctr", DoubleType(), True),
])

DISCOVERY_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("nickname", StringType(), True),
    StructField("followers", LongType(), True),
    StructField("following", LongType(), True),
    StructField("likes_total", LongType(), True),
    StructField("bio", StringType(), True),
    StructField("avatar_url", StringType(), True),
    StructField("verified", BooleanType(), True),
    StructField("discovered_from", StringType(), True),
    StructField("discovery_score", DoubleType(), True),
    StructField("predicted_niche", StringType(), True),
    StructField("discovery_round", LongType(), True),
    StructField("sample_video_id", StringType(), True),
    StructField("sample_video_views", LongType(), True),
    StructField("sample_video_engagement", DoubleType(), True),
])


def create_spark_session() -> SparkSession:
    """Create Spark session with Iceberg + Kafka + S3 configs."""
    
    spark = SparkSession.builder \
        .appName("Kafka-to-Bronze-TikTok") \
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
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_kafka_batch(spark: SparkSession, topic: str) -> "DataFrame":
    """Read all data from Kafka topic in batch mode."""
    
    print(f"\n📥 Reading from Kafka topic: {topic}")
    
    df = spark.read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "redpanda:9092") \
        .option("subscribe", topic) \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()
    
    count = df.count()
    print(f"   Found {count} records")
    
    return df


def create_iceberg_table_if_not_exists(spark: SparkSession, table_name: str, schema: StructType):
    """Create Iceberg table if it doesn't exist."""
    
    # Build CREATE TABLE statement
    columns = []
    for field in schema.fields:
        spark_type = field.dataType.simpleString()
        # Map Spark types to Iceberg/Hive types
        if spark_type == "string":
            col_type = "STRING"
        elif spark_type == "long" or spark_type == "bigint":
            col_type = "BIGINT"
        elif spark_type == "double":
            col_type = "DOUBLE"
        elif spark_type == "boolean":
            col_type = "BOOLEAN"
        elif spark_type == "timestamp":
            col_type = "TIMESTAMP"
        elif spark_type == "date":
            col_type = "DATE"
        else:
            col_type = "STRING"
        columns.append(f"{field.name} {col_type}")
    
    # Add metadata columns
    columns.append("ingest_ts TIMESTAMP")
    columns.append("dt DATE")
    
    columns_sql = ",\n    ".join(columns)
    
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        {columns_sql}
    )
    USING iceberg
    PARTITIONED BY (dt)
    """
    
    print(f"\n🔨 Creating table: {table_name}")
    spark.sql(create_sql)
    print(f"   ✅ Table ready")


def load_profiles(spark: SparkSession):
    """Load TikTok profiles from Kafka to Bronze."""
    
    topic = "kol.profiles.raw"
    table = "kol_lake.kol_bronze.tiktok_profiles"
    
    print("\n" + "=" * 70)
    print("📊 LOADING: TikTok Profiles")
    print("=" * 70)
    
    # Read from Kafka
    kafka_df = read_kafka_batch(spark, topic)
    
    if kafka_df.count() == 0:
        print("   ⚠️ No data to process")
        return 0
    
    # Parse JSON value
    df = kafka_df.select(
        col("value").cast("string").alias("json_value"),
        col("timestamp").alias("kafka_ts")
    )
    
    df = df.select(
        from_json(col("json_value"), PROFILE_SCHEMA).alias("data"),
        col("kafka_ts")
    ).select("data.*", "kafka_ts")
    
    # Add metadata columns
    df = df.withColumn("ingest_ts", current_timestamp()) \
           .withColumn("dt", to_date(current_timestamp()))
    
    # Create table and write
    create_iceberg_table_if_not_exists(spark, table, PROFILE_SCHEMA)
    
    # Dedupe by username (keep latest)
    df = df.dropDuplicates(["username"])
    
    record_count = df.count()
    print(f"\n📤 Writing {record_count} profiles to {table}")
    
    df.writeTo(table).append()
    
    print(f"   ✅ Done!")
    return record_count


def load_videos(spark: SparkSession):
    """Load TikTok videos from Kafka to Bronze."""
    
    topic = "kol.videos.raw"
    table = "kol_lake.kol_bronze.tiktok_videos"
    
    print("\n" + "=" * 70)
    print("📊 LOADING: TikTok Videos")
    print("=" * 70)
    
    kafka_df = read_kafka_batch(spark, topic)
    
    if kafka_df.count() == 0:
        print("   ⚠️ No data to process")
        return 0
    
    df = kafka_df.select(
        col("value").cast("string").alias("json_value"),
        col("timestamp").alias("kafka_ts")
    )
    
    df = df.select(
        from_json(col("json_value"), VIDEO_SCHEMA).alias("data"),
        col("kafka_ts")
    ).select("data.*", "kafka_ts")
    
    df = df.withColumn("ingest_ts", current_timestamp()) \
           .withColumn("dt", to_date(current_timestamp()))
    
    create_iceberg_table_if_not_exists(spark, table, VIDEO_SCHEMA)
    
    # Dedupe by video_id
    df = df.dropDuplicates(["video_id"])
    
    record_count = df.count()
    print(f"\n📤 Writing {record_count} videos to {table}")
    
    df.writeTo(table).append()
    
    print(f"   ✅ Done!")
    return record_count


def load_comments(spark: SparkSession):
    """Load TikTok comments from Kafka to Bronze."""
    
    topic = "kol.comments.raw"
    table = "kol_lake.kol_bronze.tiktok_comments"
    
    print("\n" + "=" * 70)
    print("📊 LOADING: TikTok Comments")
    print("=" * 70)
    
    kafka_df = read_kafka_batch(spark, topic)
    
    if kafka_df.count() == 0:
        print("   ⚠️ No data to process")
        return 0
    
    df = kafka_df.select(
        col("value").cast("string").alias("json_value"),
        col("timestamp").alias("kafka_ts")
    )
    
    df = df.select(
        from_json(col("json_value"), COMMENT_SCHEMA).alias("data"),
        col("kafka_ts")
    ).select("data.*", "kafka_ts")
    
    df = df.withColumn("ingest_ts", current_timestamp()) \
           .withColumn("dt", to_date(current_timestamp()))
    
    create_iceberg_table_if_not_exists(spark, table, COMMENT_SCHEMA)
    
    # Dedupe by event_id
    df = df.dropDuplicates(["event_id"])
    
    record_count = df.count()
    print(f"\n📤 Writing {record_count} comments to {table}")
    
    df.writeTo(table).append()
    
    print(f"   ✅ Done!")
    return record_count


def load_products(spark: SparkSession):
    """Load TikTok products from Kafka to Bronze."""
    
    topic = "kol.products.raw"
    table = "kol_lake.kol_bronze.tiktok_products"
    
    print("\n" + "=" * 70)
    print("📊 LOADING: TikTok Products")
    print("=" * 70)
    
    kafka_df = read_kafka_batch(spark, topic)
    
    if kafka_df.count() == 0:
        print("   ⚠️ No data to process")
        return 0
    
    df = kafka_df.select(
        col("value").cast("string").alias("json_value"),
        col("timestamp").alias("kafka_ts")
    )
    
    df = df.select(
        from_json(col("json_value"), PRODUCT_SCHEMA).alias("data"),
        col("kafka_ts")
    ).select("data.*", "kafka_ts")
    
    df = df.withColumn("ingest_ts", current_timestamp()) \
           .withColumn("dt", to_date(current_timestamp()))
    
    create_iceberg_table_if_not_exists(spark, table, PRODUCT_SCHEMA)
    
    # Dedupe by product_id + video_id
    df = df.dropDuplicates(["product_id", "video_id"])
    
    record_count = df.count()
    print(f"\n📤 Writing {record_count} products to {table}")
    
    df.writeTo(table).append()
    
    print(f"   ✅ Done!")
    return record_count


def load_discovery(spark: SparkSession):
    """Load TikTok discovery from Kafka to Bronze."""
    
    topic = "kol.discovery.raw"
    table = "kol_lake.kol_bronze.tiktok_discovery"
    
    print("\n" + "=" * 70)
    print("📊 LOADING: TikTok Discovery")
    print("=" * 70)
    
    kafka_df = read_kafka_batch(spark, topic)
    
    if kafka_df.count() == 0:
        print("   ⚠️ No data to process")
        return 0
    
    df = kafka_df.select(
        col("value").cast("string").alias("json_value"),
        col("timestamp").alias("kafka_ts")
    )
    
    df = df.select(
        from_json(col("json_value"), DISCOVERY_SCHEMA).alias("data"),
        col("kafka_ts")
    ).select("data.*", "kafka_ts")
    
    df = df.withColumn("ingest_ts", current_timestamp()) \
           .withColumn("dt", to_date(current_timestamp()))
    
    create_iceberg_table_if_not_exists(spark, table, DISCOVERY_SCHEMA)
    
    # Dedupe by username
    df = df.dropDuplicates(["username"])
    
    record_count = df.count()
    print(f"\n📤 Writing {record_count} discovery records to {table}")
    
    df.writeTo(table).append()
    
    print(f"   ✅ Done!")
    return record_count


def main():
    parser = argparse.ArgumentParser(description="Load TikTok data from Kafka to Bronze Iceberg")
    parser.add_argument("--topic", type=str, default="all",
                       choices=["all", "profiles", "videos", "comments", "products", "discovery"],
                       help="Which topic to load (default: all)")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("🚀 KAFKA TO BRONZE ICEBERG - TikTok Data ETL")
    print("=" * 70)
    print(f"   Start time: {datetime.now()}")
    print(f"   Topic: {args.topic}")
    
    spark = create_spark_session()
    
    # Ensure schema exists
    spark.sql("CREATE DATABASE IF NOT EXISTS kol_lake.kol_bronze")
    
    results = {}
    
    if args.topic in ["all", "profiles"]:
        results["profiles"] = load_profiles(spark)
    
    if args.topic in ["all", "videos"]:
        results["videos"] = load_videos(spark)
    
    if args.topic in ["all", "comments"]:
        results["comments"] = load_comments(spark)
    
    if args.topic in ["all", "products"]:
        results["products"] = load_products(spark)
    
    if args.topic in ["all", "discovery"]:
        results["discovery"] = load_discovery(spark)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 ETL SUMMARY")
    print("=" * 70)
    for topic, count in results.items():
        status = "✅" if count > 0 else "⚠️"
        print(f"   {status} {topic}: {count} records")
    
    total = sum(results.values())
    print(f"\n   Total: {total} records loaded to Bronze")
    print(f"   End time: {datetime.now()}")
    print("=" * 70)
    
    spark.stop()


if __name__ == "__main__":
    main()

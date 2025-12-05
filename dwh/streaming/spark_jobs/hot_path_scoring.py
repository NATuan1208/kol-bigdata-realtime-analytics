"""
Hot Path Scoring - Spark Structured Streaming Job
==================================================

DOMAIN: KOL Analytics Real-time Scoring Pipeline

This job processes KOL events from Kafka in real-time:
1. Reads from Redpanda/Kafka topics (kol.profiles.raw, kol.videos.raw)
2. Extracts features from JSON events  
3. Calls REST API for ML scoring (Trust, Success, Trending)
4. Writes results to Kafka topic (scores.stream) and Redis cache

Flow:
    Kafka (kol.profiles.raw) 
        → Parse JSON 
        → Extract Features 
        → HTTP Call to /predict/kol-score 
        → Kafka (scores.stream) + Redis Cache

Usage:
    # From Spark container
    docker exec kol-spark-master spark-submit \\
        --master spark://spark-master:7077 \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \\
        --conf spark.executor.memory=1g \\
        --conf spark.driver.memory=1g \\
        /opt/spark-jobs/hot_path_scoring.py

    # Local development
    spark-submit \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \\
        hot_path_scoring.py --mode local

Environment Variables:
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (default: redpanda:9092)
    API_URL: Scoring API base URL (default: http://api:8080)
    REDIS_HOST: Redis host (default: redis)
    REDIS_PORT: Redis port (default: 6379)
    CHECKPOINT_DIR: Spark checkpoint directory (default: /opt/spark/checkpoints/hot_path)
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Iterator

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, from_json, to_json, struct, lit, current_timestamp,
    udf, when, coalesce, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, DoubleType, 
    BooleanType, TimestampType, MapType, IntegerType
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HotPathScoring")


# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    """Configuration from environment variables"""
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    
    # Input topics
    INPUT_TOPIC_PROFILES = os.getenv("INPUT_TOPIC_PROFILES", "kol.profiles.raw")
    INPUT_TOPIC_VIDEOS = os.getenv("INPUT_TOPIC_VIDEOS", "kol.videos.raw")
    
    # Output
    OUTPUT_TOPIC_SCORES = os.getenv("OUTPUT_TOPIC_SCORES", "scores.stream")
    
    # API
    API_URL = os.getenv("API_URL", "http://api:8080")
    API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "5"))
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", "3600"))  # 1 hour
    
    # Spark Streaming
    CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/tmp/spark_checkpoints/hot_path")
    TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL", "10 seconds")
    WATERMARK_DELAY = os.getenv("WATERMARK_DELAY", "5 minutes")
    
    # Processing
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))


# ============================================================================
# SCHEMAS
# ============================================================================

# Input schema for kol.profiles.raw (supports both raw strings and integers)
PROFILE_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("user_id", StringType(), True),
    # Support both numeric fields and raw string formats
    StructField("followers_count", LongType(), True),
    StructField("following_count", LongType(), True),
    StructField("post_count", LongType(), True),
    StructField("favorites_count", LongType(), True),
    # Raw string formats from TikTok scraper
    StructField("followers_raw", StringType(), True),
    StructField("following_raw", StringType(), True),
    StructField("likes_raw", StringType(), True),
    StructField("verified", BooleanType(), True),
    StructField("bio", StringType(), True),
    StructField("profile_url", StringType(), True),
    StructField("nickname", StringType(), True),
    StructField("signature", StringType(), True),
    StructField("avatar_url", StringType(), True),
])

# Input schema for kol.videos.raw
VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("username", StringType(), True),
    StructField("caption", StringType(), True),
    StructField("view_count", LongType(), True),
    StructField("like_count", LongType(), True),
    StructField("comment_count", LongType(), True),
    StructField("share_count", LongType(), True),
])

# Output schema for scores.stream
SCORE_OUTPUT_SCHEMA = StructType([
    StructField("kol_id", StringType(), False),
    StructField("platform", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("trust_score", DoubleType(), True),
    StructField("trust_label", StringType(), True),
    StructField("trust_confidence", DoubleType(), True),
    StructField("success_score", DoubleType(), True),
    StructField("success_label", StringType(), True),
    StructField("success_confidence", DoubleType(), True),
    StructField("trending_score", DoubleType(), True),
    StructField("trending_label", StringType(), True),
    StructField("trending_growth", DoubleType(), True),
    StructField("latency_ms", IntegerType(), True),
    StructField("model_version_trust", StringType(), True),
    StructField("model_version_success", StringType(), True),
])


# ============================================================================
# SPARK SESSION
# ============================================================================
def create_spark_session(app_name: str = "KOL-HotPath-Scoring", local: bool = False) -> SparkSession:
    """Create Spark session with Kafka packages"""
    
    builder = SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.streaming.checkpointLocation", Config.CHECKPOINT_DIR) \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
    
    if local:
        builder = builder.master("local[*]")
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    
    logger.info(f"✅ Created Spark session: {app_name}")
    logger.info(f"   Kafka: {Config.KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"   API: {Config.API_URL}")
    
    return spark


# ============================================================================
# KAFKA READER
# ============================================================================
def read_kafka_stream(spark: SparkSession, topic: str) -> DataFrame:
    """Read streaming data from Kafka topic"""
    
    return spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", Config.KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .option("maxOffsetsPerTrigger", Config.BATCH_SIZE * 10) \
        .load()


def parse_profile_events(df: DataFrame) -> DataFrame:
    """Parse profile events from Kafka JSON - handles both raw strings and integers"""
    
    # UDF to parse raw follower strings like "11.3K", "1.3M", etc.
    @udf(LongType())
    def parse_raw_count(raw_str: str) -> int:
        if raw_str is None:
            return 0
        try:
            # Remove commas
            raw_str = str(raw_str).replace(",", "").strip()
            
            # Handle K (thousands)
            if raw_str.upper().endswith("K"):
                return int(float(raw_str[:-1]) * 1000)
            # Handle M (millions)
            elif raw_str.upper().endswith("M"):
                return int(float(raw_str[:-1]) * 1000000)
            # Handle B (billions)
            elif raw_str.upper().endswith("B"):
                return int(float(raw_str[:-1]) * 1000000000)
            else:
                return int(float(raw_str))
        except (ValueError, TypeError):
            return 0
    
    parsed_df = df \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp") \
        .select(
            from_json(col("json_str"), PROFILE_SCHEMA).alias("data"),
            col("kafka_timestamp")
        )
    
    # Use numeric fields if available, otherwise parse raw strings
    return parsed_df.select(
        col("data.username").alias("kol_id"),
        col("data.platform"),
        # Prefer followers_count if available, else parse followers_raw
        when(col("data.followers_count").isNotNull(), col("data.followers_count"))
            .otherwise(parse_raw_count(col("data.followers_raw")))
            .alias("followers_count"),
        when(col("data.following_count").isNotNull(), col("data.following_count"))
            .otherwise(parse_raw_count(col("data.following_raw")))
            .alias("following_count"),
        coalesce(col("data.post_count"), lit(0)).alias("post_count"),
        # For favorites, use likes_raw if favorites_count not available
        when(col("data.favorites_count").isNotNull(), col("data.favorites_count"))
            .otherwise(parse_raw_count(col("data.likes_raw")))
            .alias("favorites_count"),
        coalesce(col("data.verified"), lit(False)).alias("verified"),
        col("data.bio"),
        col("data.signature"),
        col("kafka_timestamp")
    ).filter(col("kol_id").isNotNull())


def parse_video_events(df: DataFrame) -> DataFrame:
    """Parse video events from Kafka JSON"""
    
    return df \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp") \
        .select(
            from_json(col("json_str"), VIDEO_SCHEMA).alias("data"),
            col("kafka_timestamp")
        ) \
        .select(
            col("data.username").alias("kol_id"),
            col("data.platform"),
            col("data.video_id"),
            col("data.view_count"),
            col("data.like_count"),
            col("data.comment_count"),
            col("data.share_count"),
            col("kafka_timestamp")
        ) \
        .filter(col("kol_id").isNotNull())


# ============================================================================
# SCORING FUNCTIONS
# ============================================================================
def call_scoring_api(
    kol_id: str,
    followers_count: int,
    following_count: int,
    post_count: int,
    favorites_count: int,
    verified: bool,
    bio: Optional[str],
    avg_views: int = 0,
    avg_likes: int = 0,
    avg_comments: int = 0,
    avg_shares: int = 0
) -> Dict[str, Any]:
    """
    Call the scoring API to get Trust, Success, and Trending scores.
    
    This function is called for each KOL profile event.
    """
    import requests
    import time
    
    start_time = time.time()
    
    # Prepare request payload
    # Estimate account_age_days (assume 1 year if unknown)
    account_age_days = 365  # Default, should be calculated from profile creation date
    
    # Calculate bio length
    bio_length = len(bio) if bio else 0
    has_bio = bool(bio and len(bio) > 0)
    
    payload = {
        "kol_id": kol_id,
        "followers_count": followers_count or 0,
        "following_count": following_count or 0,
        "post_count": post_count or 0,
        "favorites_count": favorites_count or 0,
        "account_age_days": account_age_days,
        "verified": verified or False,
        "has_bio": has_bio,
        "has_url": False,  # TODO: Extract from profile
        "has_profile_image": True,  # Assume true if profile exists
        "bio_length": bio_length,
    }
    
    result = {
        "kol_id": kol_id,
        "trust_score": None,
        "trust_label": "Unknown",
        "trust_confidence": 0.0,
        "success_score": None,
        "success_label": "Unknown",
        "success_confidence": 0.0,
        "trending_score": None,
        "trending_label": "Unknown",
        "trending_growth": 0.0,
        "latency_ms": 0,
        "model_version_trust": "unknown",
        "model_version_success": "unknown",
        "error": None
    }
    
    try:
        # Call Trust Score API
        trust_url = f"{Config.API_URL}/predict/trust"
        trust_response = requests.post(
            trust_url,
            json=payload,
            timeout=Config.API_TIMEOUT_SECONDS
        )
        
        if trust_response.status_code == 200:
            trust_data = trust_response.json()
            result["trust_score"] = trust_data.get("trust_score")
            result["trust_label"] = trust_data.get("risk_level", "Unknown")
            result["trust_confidence"] = trust_data.get("confidence", 0.0)
            result["model_version_trust"] = trust_data.get("model_version", "unknown")
        else:
            logger.warning(f"Trust API returned {trust_response.status_code}: {trust_response.text}")
            
    except requests.exceptions.Timeout:
        logger.warning(f"Trust API timeout for {kol_id}")
        result["error"] = "timeout"
    except requests.exceptions.RequestException as e:
        logger.warning(f"Trust API error for {kol_id}: {e}")
        result["error"] = str(e)
    
    # TODO: Call Success Score API when deployed
    # TODO: Call Trending Score API when deployed
    
    # Calculate latency
    latency_ms = int((time.time() - start_time) * 1000)
    result["latency_ms"] = latency_ms
    
    return result


# Create UDF for scoring
def create_scoring_udf():
    """Create Spark UDF for scoring API calls"""
    
    from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
    
    output_schema = StructType([
        StructField("kol_id", StringType(), False),
        StructField("trust_score", DoubleType(), True),
        StructField("trust_label", StringType(), True),
        StructField("trust_confidence", DoubleType(), True),
        StructField("success_score", DoubleType(), True),
        StructField("success_label", StringType(), True),
        StructField("success_confidence", DoubleType(), True),
        StructField("trending_score", DoubleType(), True),
        StructField("trending_label", StringType(), True),
        StructField("trending_growth", DoubleType(), True),
        StructField("latency_ms", IntegerType(), True),
        StructField("model_version_trust", StringType(), True),
        StructField("model_version_success", StringType(), True),
        StructField("error", StringType(), True),
    ])
    
    @udf(output_schema)
    def score_kol(
        kol_id: str,
        followers_count: int,
        following_count: int,
        post_count: int,
        favorites_count: int,
        verified: bool,
        bio: str
    ):
        return call_scoring_api(
            kol_id=kol_id,
            followers_count=followers_count,
            following_count=following_count,
            post_count=post_count,
            favorites_count=favorites_count,
            verified=verified,
            bio=bio
        )
    
    return score_kol


# ============================================================================
# BATCH PROCESSING (for foreachBatch)
# ============================================================================
def process_profile_batch(batch_df: DataFrame, batch_id: int):
    """
    Process a micro-batch of profile events.
    
    For each profile:
    1. Call scoring API
    2. Write to Kafka output topic
    3. Cache in Redis
    """
    if batch_df.isEmpty():
        logger.info(f"Batch {batch_id}: Empty, skipping")
        return
    
    count = batch_df.count()
    logger.info(f"Batch {batch_id}: Processing {count} profiles")
    
    # Get scoring UDF
    score_udf = create_scoring_udf()
    
    # Apply scoring
    scored_df = batch_df.withColumn(
        "scores",
        score_udf(
            col("kol_id"),
            col("followers_count"),
            col("following_count"),
            col("post_count"),
            col("favorites_count"),
            col("verified"),
            col("bio")
        )
    )
    
    # Flatten scores
    output_df = scored_df.select(
        col("kol_id"),
        col("platform"),
        current_timestamp().cast("string").alias("timestamp"),
        col("scores.trust_score").alias("trust_score"),
        col("scores.trust_label").alias("trust_label"),
        col("scores.trust_confidence").alias("trust_confidence"),
        col("scores.success_score").alias("success_score"),
        col("scores.success_label").alias("success_label"),
        col("scores.success_confidence").alias("success_confidence"),
        col("scores.trending_score").alias("trending_score"),
        col("scores.trending_label").alias("trending_label"),
        col("scores.trending_growth").alias("trending_growth"),
        col("scores.latency_ms").alias("latency_ms"),
        col("scores.model_version_trust").alias("model_version_trust"),
        col("scores.model_version_success").alias("model_version_success"),
    )
    
    # Write to Kafka output topic
    output_df \
        .select(
            col("kol_id").alias("key"),
            to_json(struct("*")).alias("value")
        ) \
        .write \
        .format("kafka") \
        .option("kafka.bootstrap.servers", Config.KAFKA_BOOTSTRAP_SERVERS) \
        .option("topic", Config.OUTPUT_TOPIC_SCORES) \
        .save()
    
    logger.info(f"Batch {batch_id}: Written {count} scores to {Config.OUTPUT_TOPIC_SCORES}")
    
    # Cache to Redis (optional)
    try:
        cache_to_redis(output_df)
    except Exception as e:
        logger.warning(f"Redis cache failed: {e}")


def cache_to_redis(df: DataFrame):
    """Cache scores to Redis for fast lookup"""
    import redis
    
    r = redis.Redis(
        host=Config.REDIS_HOST,
        port=Config.REDIS_PORT,
        decode_responses=True
    )
    
    # Collect and cache
    rows = df.collect()
    
    pipe = r.pipeline()
    for row in rows:
        key = f"kol:score:{row['kol_id']}"
        value = json.dumps({
            "trust_score": row["trust_score"],
            "trust_label": row["trust_label"],
            "success_score": row["success_score"],
            "trending_score": row["trending_score"],
            "timestamp": row["timestamp"],
        })
        pipe.setex(key, Config.REDIS_TTL_SECONDS, value)
    
    pipe.execute()
    logger.info(f"Cached {len(rows)} scores to Redis")


# ============================================================================
# MAIN STREAMING JOB
# ============================================================================
def run_hot_path_scoring(spark: SparkSession, mode: str = "streaming"):
    """
    Main streaming job: Read profiles → Score → Output
    
    Args:
        spark: SparkSession
        mode: "streaming" for continuous, "batch" for one-time
    """
    logger.info("🚀 Starting Hot Path Scoring Job...")
    logger.info(f"   Mode: {mode}")
    logger.info(f"   Input: {Config.INPUT_TOPIC_PROFILES}")
    logger.info(f"   Output: {Config.OUTPUT_TOPIC_SCORES}")
    
    # Read from Kafka
    raw_df = read_kafka_stream(spark, Config.INPUT_TOPIC_PROFILES)
    
    # Parse JSON events
    profiles_df = parse_profile_events(raw_df)
    
    # Add watermark for late data handling
    profiles_with_watermark = profiles_df \
        .withWatermark("kafka_timestamp", Config.WATERMARK_DELAY)
    
    if mode == "streaming":
        # Streaming mode: foreachBatch for API calls
        query = profiles_with_watermark \
            .writeStream \
            .outputMode("append") \
            .trigger(processingTime=Config.TRIGGER_INTERVAL) \
            .foreachBatch(process_profile_batch) \
            .option("checkpointLocation", f"{Config.CHECKPOINT_DIR}/profiles") \
            .start()
        
        logger.info(f"✅ Streaming query started: {query.id}")
        logger.info(f"   Trigger: {Config.TRIGGER_INTERVAL}")
        logger.info(f"   Checkpoint: {Config.CHECKPOINT_DIR}/profiles")
        
        # Wait for termination
        query.awaitTermination()
        
    else:
        # Batch mode: Process existing data once
        logger.info("Running in batch mode (one-time processing)")
        
        # Read all available data
        batch_df = spark \
            .read \
            .format("kafka") \
            .option("kafka.bootstrap.servers", Config.KAFKA_BOOTSTRAP_SERVERS) \
            .option("subscribe", Config.INPUT_TOPIC_PROFILES) \
            .option("startingOffsets", "earliest") \
            .load()
        
        profiles_batch = parse_profile_events(batch_df)
        process_profile_batch(profiles_batch, 0)
        
        logger.info("Batch processing complete")


# ============================================================================
# DEBUG MODE: Console output instead of Kafka
# ============================================================================
def run_debug_mode(spark: SparkSession):
    """
    Debug mode: Print parsed events to console (no API calls)
    """
    logger.info("🔍 Starting Debug Mode (console output only)...")
    
    # Read from Kafka
    raw_df = read_kafka_stream(spark, Config.INPUT_TOPIC_PROFILES)
    
    # Parse JSON events
    profiles_df = parse_profile_events(raw_df)
    
    # Write to console
    query = profiles_df \
        .writeStream \
        .outputMode("append") \
        .format("console") \
        .option("truncate", False) \
        .trigger(processingTime="5 seconds") \
        .start()
    
    logger.info("Debug query started - printing to console")
    query.awaitTermination()


# ============================================================================
# ENTRY POINT
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="KOL Hot Path Scoring Job")
    parser.add_argument(
        "--mode", 
        choices=["streaming", "batch", "debug", "local"],
        default="streaming",
        help="Execution mode"
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Override input topic"
    )
    
    args = parser.parse_args()
    
    # Override config if provided
    if args.topic:
        Config.INPUT_TOPIC_PROFILES = args.topic
    
    # Create Spark session
    is_local = args.mode == "local"
    spark = create_spark_session(local=is_local)
    
    try:
        if args.mode == "debug":
            run_debug_mode(spark)
        elif args.mode == "local":
            # Local mode with local Kafka
            Config.KAFKA_BOOTSTRAP_SERVERS = "localhost:19092"
            Config.API_URL = "http://localhost:8000"
            run_hot_path_scoring(spark, mode="streaming")
        else:
            run_hot_path_scoring(spark, mode=args.mode)
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        spark.stop()
        logger.info("Spark session stopped")


if __name__ == "__main__":
    main()

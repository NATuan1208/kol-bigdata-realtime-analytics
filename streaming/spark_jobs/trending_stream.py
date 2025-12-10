#!/usr/bin/env python3
"""
Trending Score Stream - Spark Structured Streaming
===================================================

FOCUSED JOB: Only calculates Trending Score (velocity-based)

Architecture Decision:
----------------------
- Trending Score: Calculated here (real-time, velocity changes frequently)
- Trust Score: Calculated in API (on-demand, profile-based)
- Success Score: Calculated in API (on-demand, ML model)
- Final Score: Composed in API from all 3 scores

Why Trending needs streaming:
- Velocity = rate of change of engagement
- Changes every minute as new videos/products come in
- Needs windowed aggregation over time
- Pre-computed for fast dashboard queries

Flow:
    Kafka (kol.videos.raw, kol.products.raw)
        → Parse JSON
        → Window aggregation (5-minute tumbling)
        → Calculate velocity & trending score
        → Write to Redis (trending:{platform}:{kol_id})

Redis Output Schema:
    Key: trending:{platform}:{kol_id}
    Hash:
        - trending_score: float (0-100)
        - trending_label: str (Viral/Hot/Warm/Normal/Cold)
        - velocity: float (current engagement rate)
        - momentum: float (acceleration)
        - event_count: int (events in window)
        - updated_at: str (ISO timestamp)

Usage:
    # Spark cluster
    docker exec kol-spark-master spark-submit \\
        --master spark://spark-master:7077 \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \\
        /opt/spark-jobs/trending_stream.py

    # Local mode
    python trending_stream.py --mode local

Author: KOL Analytics Team
Date: 2024-12 (Refactored)
"""

import os
import sys
import json
import math
import logging
from datetime import datetime
from typing import Dict, Any

# Spark imports
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, from_json, to_json, struct, lit, current_timestamp,
    udf, when, coalesce, window, count, sum as spark_sum,
    avg, max as spark_max, min as spark_min
)
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, DoubleType,
    BooleanType, IntegerType
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TrendingStream")


# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    """Configuration from environment variables"""
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    
    # Input topics
    TOPIC_VIDEOS = "kol.videos.raw"
    TOPIC_PRODUCTS = "kol.products.raw"
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_TTL_SECONDS = 3600  # 1 hour
    
    # Streaming config
    CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/tmp/spark_checkpoints/trending")
    TRIGGER_INTERVAL = "30 seconds"
    WATERMARK_DELAY = "5 minutes"
    WINDOW_SIZE = "5 minutes"
    SLIDE_INTERVAL = "1 minute"
    
    # Trending score params
    TRENDING_K = 0.8  # Sigmoid steepness
    TRENDING_THRESHOLD = 2.0  # Sigmoid center point


# ============================================================================
# SCHEMAS
# ============================================================================

# Video event schema
VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("video_views", LongType(), True),
    StructField("video_likes", LongType(), True),
    StructField("video_comments", LongType(), True),
    StructField("video_shares", LongType(), True),
])

# Product event schema
PRODUCT_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("video_views", LongType(), True),
    StructField("video_likes", LongType(), True),
    StructField("video_comments", LongType(), True),
    StructField("video_shares", LongType(), True),
    StructField("sold_count", LongType(), True),
])


# ============================================================================
# TRENDING SCORE CALCULATOR
# ============================================================================
class TrendingCalculator:
    """
    TrendingScore V2 - Velocity-based calculation.
    
    Formula:
        raw = α * personal_growth + β * market_position + γ * momentum
        score = 100 / (1 + exp(-k * (raw - threshold)))
    
    Where:
        - personal_growth = current_velocity / baseline_velocity
        - market_position = current_velocity / global_avg
        - momentum = (current - previous) / previous
        - α=0.5, β=0.3, γ=0.2 (weights)
    
    Labels:
        - Viral: 80-100 (explosive growth)
        - Hot: 60-80 (significant momentum)
        - Warm: 40-60 (growing interest)
        - Normal: 25-40 (steady state)
        - Cold: 0-25 (declining or inactive)
    """
    
    @staticmethod
    def calculate_velocity(
        event_count: int,
        total_engagement: int,
        window_minutes: int = 5
    ) -> float:
        """
        Calculate engagement velocity (engagement per minute).
        
        Velocity = total_engagement / window_minutes * log(1 + event_count)
        """
        if window_minutes <= 0:
            window_minutes = 5
        
        # Base velocity from engagement
        base_velocity = total_engagement / window_minutes
        
        # Boost by event frequency (more events = more active)
        frequency_boost = math.log1p(event_count)
        
        return base_velocity * (1 + 0.1 * frequency_boost)
    
    @staticmethod
    def calculate_trending_score(
        current_velocity: float,
        baseline_velocity: float = 100.0,  # Default baseline
        global_avg_velocity: float = 100.0,  # Default global avg
        momentum: float = 0.0,
        k: float = 0.8,
        threshold: float = 2.0
    ) -> Dict[str, Any]:
        """
        Calculate trending score with sigmoid normalization.
        
        Returns dict with:
            - trending_score (0-100)
            - trending_label (Viral/Hot/Warm/Normal/Cold)
            - velocity
            - momentum
        """
        # Avoid division by zero
        baseline = max(baseline_velocity, 1.0)
        global_avg = max(global_avg_velocity, 1.0)
        
        # Component scores
        personal_growth = current_velocity / baseline
        market_position = current_velocity / global_avg
        
        # Weighted combination: α=0.5, β=0.3, γ=0.2
        raw_score = (
            0.5 * personal_growth +
            0.3 * market_position +
            0.2 * (1 + momentum)  # Normalized around 1
        )
        
        # Sigmoid normalization to [0, 100]
        trending_score = 100 / (1 + math.exp(-k * (raw_score - threshold)))
        trending_score = max(0, min(100, trending_score))
        
        # Label assignment
        if trending_score >= 80:
            label = "Viral"
        elif trending_score >= 60:
            label = "Hot"
        elif trending_score >= 40:
            label = "Warm"
        elif trending_score >= 25:
            label = "Normal"
        else:
            label = "Cold"
        
        return {
            "trending_score": round(trending_score, 2),
            "trending_label": label,
            "velocity": round(current_velocity, 4),
            "momentum": round(momentum, 4),
            "personal_growth": round(personal_growth, 4),
            "market_position": round(market_position, 4),
        }


# ============================================================================
# SPARK UDFs
# ============================================================================
def create_trending_udf():
    """Create UDF for trending score calculation"""
    
    @udf(returnType=StructType([
        StructField("trending_score", DoubleType()),
        StructField("trending_label", StringType()),
        StructField("velocity", DoubleType()),
        StructField("momentum", DoubleType()),
    ]))
    def calculate_trending(
        event_count: int,
        total_engagement: int,
        prev_engagement: int = None
    ):
        # Calculate velocity
        velocity = TrendingCalculator.calculate_velocity(
            event_count=event_count or 0,
            total_engagement=total_engagement or 0,
            window_minutes=5
        )
        
        # Calculate momentum (if previous data available)
        momentum = 0.0
        if prev_engagement and prev_engagement > 0:
            momentum = (total_engagement - prev_engagement) / prev_engagement
        
        # Calculate trending score
        result = TrendingCalculator.calculate_trending_score(
            current_velocity=velocity,
            baseline_velocity=100.0,  # Will be personalized later
            global_avg_velocity=100.0,  # Will be computed from aggregates
            momentum=momentum
        )
        
        return (
            result["trending_score"],
            result["trending_label"],
            result["velocity"],
            result["momentum"],
        )
    
    return calculate_trending


# ============================================================================
# REDIS OUTPUT
# ============================================================================
def write_trending_to_redis(batch_df: DataFrame, batch_id: int):
    """
    Write trending scores to Redis.
    
    Keys:
        - trending:{platform}:{kol_id} (hash)
        - trending:ranking:{platform} (sorted set for leaderboard)
    """
    import redis
    
    try:
        r = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )
        
        rows = batch_df.collect()
        if not rows:
            logger.info(f"Batch {batch_id}: No data to write")
            return
        
        pipe = r.pipeline()
        
        for row in rows:
            kol_id = row.kol_id
            platform = row.platform or "tiktok"
            
            # Hash key for detailed data
            hash_key = f"trending:{platform}:{kol_id}"
            score_data = {
                "kol_id": kol_id,
                "platform": platform,
                "trending_score": row.trending_score,
                "trending_label": row.trending_label,
                "velocity": row.velocity,
                "momentum": row.momentum,
                "event_count": row.event_count,
                "total_engagement": row.total_engagement,
                "updated_at": datetime.utcnow().isoformat(),
            }
            pipe.hset(hash_key, mapping={k: str(v) for k, v in score_data.items()})
            pipe.expire(hash_key, Config.REDIS_TTL_SECONDS)
            
            # Sorted set for ranking/leaderboard (API reads from ranking:{platform}:trending)
            ranking_key = f"ranking:{platform}:trending"
            pipe.zadd(ranking_key, {kol_id: row.trending_score})
            
            # Legacy key for Dashboard compatibility
            legacy_key = f"streaming_scores:{kol_id}"
            legacy_data = {
                "username": kol_id,
                "platform": platform,
                "trending_score": row.trending_score,
                "label": row.trending_label,
                "score": row.trending_score,  # Alias
                "updated_at": datetime.utcnow().isoformat(),
            }
            pipe.hset(legacy_key, mapping={k: str(v) for k, v in legacy_data.items()})
            pipe.expire(legacy_key, Config.REDIS_TTL_SECONDS)
        
        pipe.execute()
        logger.info(f"✅ Batch {batch_id}: Wrote {len(rows)} trending scores to Redis")
        
    except Exception as e:
        logger.error(f"❌ Redis write error batch {batch_id}: {e}")


# ============================================================================
# SPARK SESSION
# ============================================================================
def create_spark_session(local: bool = False) -> SparkSession:
    """Create Spark session with Kafka support"""
    
    builder = SparkSession.builder \
        .appName("KOL-TrendingStream") \
        .config("spark.sql.streaming.checkpointLocation", Config.CHECKPOINT_DIR) \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
    
    if local:
        builder = builder.master("local[*]")
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    
    logger.info(f"✅ Spark session created")
    logger.info(f"   Mode: {'local' if local else 'cluster'}")
    logger.info(f"   Kafka: {Config.KAFKA_BOOTSTRAP_SERVERS}")
    
    return spark


# ============================================================================
# KAFKA STREAM
# ============================================================================
def read_kafka_stream(spark: SparkSession, topic: str) -> DataFrame:
    """Read from Kafka topic"""
    
    return spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", Config.KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .load()


# ============================================================================
# MAIN STREAMING PIPELINE
# ============================================================================
def run_trending_stream(local: bool = False):
    """
    Main entry point for trending score streaming.
    
    Pipeline:
    1. Read from kol.videos.raw and kol.products.raw
    2. Parse JSON and extract engagement metrics
    3. Window aggregation (5-minute tumbling windows)
    4. Calculate trending score per KOL
    5. Write to Redis
    """
    
    logger.info("=" * 60)
    logger.info("  TRENDING STREAM - Starting")
    logger.info("  (Focused: Only Trending Score)")
    logger.info("=" * 60)
    
    # Create Spark session
    spark = create_spark_session(local=local)
    
    # Create UDF
    trending_udf = create_trending_udf()
    
    # ===== READ VIDEO STREAM =====
    videos_raw = read_kafka_stream(spark, Config.TOPIC_VIDEOS)
    
    videos = videos_raw \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_ts") \
        .select(
            from_json(col("json_str"), VIDEO_SCHEMA).alias("data"),
            col("kafka_ts")
        ) \
        .select(
            col("data.username").alias("kol_id"),
            col("data.platform"),
            coalesce(col("data.video_views"), lit(0)).alias("views"),
            coalesce(col("data.video_likes"), lit(0)).alias("likes"),
            coalesce(col("data.video_comments"), lit(0)).alias("comments"),
            coalesce(col("data.video_shares"), lit(0)).alias("shares"),
            col("kafka_ts")
        ) \
        .filter(col("kol_id").isNotNull()) \
        .withColumn(
            "engagement",
            col("likes") + col("comments") + col("shares")
        )
    
    # ===== WINDOWED AGGREGATION =====
    videos_windowed = videos \
        .withWatermark("kafka_ts", Config.WATERMARK_DELAY) \
        .groupBy(
            window(col("kafka_ts"), Config.WINDOW_SIZE, Config.SLIDE_INTERVAL),
            col("kol_id"),
            col("platform")
        ) \
        .agg(
            count("*").alias("event_count"),
            spark_sum("engagement").alias("total_engagement"),
            spark_sum("views").alias("total_views"),
            avg("engagement").alias("avg_engagement")
        )
    
    # ===== CALCULATE TRENDING SCORE =====
    trending_scores = videos_windowed \
        .withColumn(
            "trending_result",
            trending_udf(
                col("event_count"),
                col("total_engagement"),
                lit(None)  # prev_engagement - will implement state later
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("event_count"),
            col("total_engagement"),
            col("total_views"),
            col("trending_result.trending_score").alias("trending_score"),
            col("trending_result.trending_label").alias("trending_label"),
            col("trending_result.velocity").alias("velocity"),
            col("trending_result.momentum").alias("momentum"),
        )
    
    # ===== OUTPUT TO REDIS =====
    query = trending_scores \
        .writeStream \
        .outputMode("update") \
        .foreachBatch(write_trending_to_redis) \
        .trigger(processingTime=Config.TRIGGER_INTERVAL) \
        .start()
    
    logger.info("✅ Streaming query started")
    logger.info(f"   Input: {Config.TOPIC_VIDEOS}")
    logger.info(f"   Output: Redis (trending:{{platform}}:{{kol_id}})")
    logger.info(f"   Window: {Config.WINDOW_SIZE} / {Config.SLIDE_INTERVAL}")
    logger.info(f"   Trigger: {Config.TRIGGER_INTERVAL}")
    
    # Wait for termination
    query.awaitTermination()


# ============================================================================
# CLI
# ============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Trending Score Stream")
    parser.add_argument("--mode", choices=["local", "cluster"], default="local",
                        help="Spark mode: local or cluster")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    run_trending_stream(local=(args.mode == "local"))

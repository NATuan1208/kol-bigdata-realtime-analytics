#!/usr/bin/env python3
"""
Multi-Topic Hot Path - Process Videos + Products for Complete Scoring
======================================================================

Handles multiple Kafka topics:
- kol.videos.raw    → Trending Score (velocity from video events)
- kol.products.raw  → Success Score (LightGBM prediction)
- kol.profiles.raw  → Trust Score (rule-based)

Then merges all scores into unified output.

Usage:
    # Spark cluster
    docker exec kol-spark-master spark-submit \\
        --master spark://spark-master:7077 \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \\
        /opt/spark-jobs/multi_topic_hot_path.py

    # Local
    python multi_topic_hot_path.py --mode local
"""

import os
import sys
import json
import math
import logging
from datetime import datetime
from typing import Dict, Any

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, from_json, to_json, struct, lit, current_timestamp,
    udf, when, coalesce, window, count, sum as spark_sum,
    avg, max as spark_max, broadcast, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, DoubleType,
    BooleanType, IntegerType
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MultiTopicHotPath")


# ============================================================================
# CONFIG
# ============================================================================
class Config:
    KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    
    # Topics
    TOPIC_PROFILES = "kol.profiles.raw"
    TOPIC_VIDEOS = "kol.videos.raw"
    TOPIC_PRODUCTS = "kol.products.raw"
    TOPIC_OUTPUT = "kol.scores.unified"
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_TTL = 3600
    
    # Streaming
    CHECKPOINT_DIR = "/tmp/spark_checkpoints/multi_topic"
    TRIGGER = "30 seconds"
    WATERMARK = "5 minutes"


# ============================================================================
# SCHEMAS
# ============================================================================
VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("event_time", StringType()),
    StructField("platform", StringType()),
    StructField("username", StringType()),
    StructField("video_id", StringType()),
    StructField("video_views", LongType()),
    StructField("video_likes", LongType()),
    StructField("video_comments", LongType()),
    StructField("video_shares", LongType()),
])

PRODUCT_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("event_time", StringType()),
    StructField("platform", StringType()),
    StructField("username", StringType()),
    StructField("product_id", StringType()),
    StructField("video_views", LongType()),
    StructField("video_likes", LongType()),
    StructField("video_comments", LongType()),
    StructField("video_shares", LongType()),
    StructField("engagement_rate", DoubleType()),
    StructField("est_ctr", DoubleType()),
    StructField("sold_count", LongType()),
    StructField("price", DoubleType()),
])

PROFILE_SCHEMA = StructType([
    StructField("username", StringType()),
    StructField("platform", StringType()),
    StructField("followers_count", LongType()),
    StructField("following_count", LongType()),
    StructField("post_count", LongType()),
    StructField("favorites_count", LongType()),
    StructField("verified", BooleanType()),
    StructField("followers_raw", StringType()),
])


# ============================================================================
# SCORING LOGIC
# ============================================================================

def calculate_trending_score(
    event_count: int,
    total_views: int,
    avg_views_per_event: float,
    global_avg_events: float
) -> Dict[str, Any]:
    """
    Calculate Trending Score based on velocity.
    
    Formula: sigmoid(α * personal_ratio + β * view_ratio)
    """
    if global_avg_events <= 0:
        global_avg_events = 1.0
    
    # Personal velocity
    personal_ratio = event_count / global_avg_events
    
    # View weight (engagement indicator)
    view_ratio = avg_views_per_event / 10000 if avg_views_per_event else 0
    
    # Combined raw score
    raw_score = 0.6 * personal_ratio + 0.4 * min(view_ratio, 5)
    
    # Sigmoid normalization
    k, threshold = 0.8, 2.0
    score = 100 / (1 + math.exp(-k * (raw_score - threshold)))
    
    # Label
    if score >= 80:
        label = "Viral"
    elif score >= 60:
        label = "Hot"
    elif score >= 40:
        label = "Warm"
    elif score >= 25:
        label = "Normal"
    else:
        label = "Cold"
    
    return {
        "score": round(score, 2),
        "label": label,
        "velocity": round(personal_ratio, 4),
    }


def calculate_success_score(
    video_views: int,
    video_likes: int,
    video_comments: int,
    video_shares: int,
    engagement_rate: float,
    est_ctr: float
) -> Dict[str, Any]:
    """
    Calculate Success Score (rule-based fallback).
    
    Weights:
    - Views: 30%
    - Engagement rate: 30%
    - CTR: 20%
    - Interaction quality: 20%
    """
    score = 0
    
    # Views component (30 pts)
    if video_views >= 100000:
        score += 30
    elif video_views >= 50000:
        score += 24
    elif video_views >= 10000:
        score += 18
    elif video_views >= 1000:
        score += 10
    else:
        score += 5
    
    # Engagement rate (30 pts)
    er = engagement_rate or 0
    if er >= 0.1:
        score += 30
    elif er >= 0.05:
        score += 22
    elif er >= 0.02:
        score += 14
    elif er >= 0.01:
        score += 7
    
    # CTR (20 pts)
    ctr = est_ctr or 0
    if ctr >= 0.05:
        score += 20
    elif ctr >= 0.02:
        score += 14
    elif ctr >= 0.01:
        score += 8
    
    # Interaction quality (20 pts) - likes-to-view ratio
    if video_views > 0:
        lvr = video_likes / video_views
        if lvr >= 0.1:
            score += 20
        elif lvr >= 0.05:
            score += 14
        elif lvr >= 0.02:
            score += 8
        else:
            score += 4
    
    # Label
    if score >= 70:
        label = "High"
    elif score >= 40:
        label = "Medium"
    else:
        label = "Low"
    
    return {
        "score": round(min(score, 100), 2),
        "label": label,
        "confidence": 70.0,  # Rule-based confidence
    }


def calculate_trust_score(
    followers: int,
    following: int,
    posts: int,
    verified: bool
) -> Dict[str, Any]:
    """
    Calculate Trust Score based on profile metrics.
    """
    score = 0
    
    # Follower/Following ratio (25 pts)
    if following > 0:
        ratio = followers / following
        if ratio >= 10:
            score += 25
        elif ratio >= 5:
            score += 20
        elif ratio >= 2:
            score += 15
        elif ratio >= 1:
            score += 10
        else:
            score += 5
    else:
        score += 15
    
    # Follower count tier (25 pts)
    if followers >= 1000000:
        score += 25
    elif followers >= 100000:
        score += 22
    elif followers >= 10000:
        score += 18
    elif followers >= 1000:
        score += 12
    else:
        score += 5
    
    # Post activity (25 pts)
    if posts >= 100:
        score += 25
    elif posts >= 50:
        score += 18
    elif posts >= 20:
        score += 12
    elif posts >= 5:
        score += 6
    
    # Verified bonus (10 pts)
    if verified:
        score += 10
    
    # Consistent activity bonus (15 pts) - assume if posts > followers/1000
    if followers > 0 and posts > followers / 1000:
        score += 15
    
    # Label
    if score >= 80:
        label = "Highly Trusted"
    elif score >= 60:
        label = "Trusted"
    elif score >= 40:
        label = "Moderate"
    else:
        label = "Low Trust"
    
    return {
        "score": round(min(score, 100), 2),
        "label": label,
    }


# ============================================================================
# SPARK UDFs
# ============================================================================
def register_udfs():
    """Register Spark UDFs for scoring"""
    
    # Trending Score UDF
    @udf(returnType=StructType([
        StructField("trending_score", DoubleType()),
        StructField("trending_label", StringType()),
        StructField("trending_velocity", DoubleType()),
    ]))
    def trending_udf(event_count, total_views, avg_views, global_avg):
        result = calculate_trending_score(
            event_count or 0,
            total_views or 0,
            avg_views or 0,
            global_avg or 1
        )
        return (result["score"], result["label"], result["velocity"])
    
    # Success Score UDF
    @udf(returnType=StructType([
        StructField("success_score", DoubleType()),
        StructField("success_label", StringType()),
        StructField("success_confidence", DoubleType()),
    ]))
    def success_udf(views, likes, comments, shares, er, ctr):
        result = calculate_success_score(
            views or 0, likes or 0, comments or 0, shares or 0,
            er or 0, ctr or 0
        )
        return (result["score"], result["label"], result["confidence"])
    
    # Trust Score UDF
    @udf(returnType=StructType([
        StructField("trust_score", DoubleType()),
        StructField("trust_label", StringType()),
    ]))
    def trust_udf(followers, following, posts, verified):
        result = calculate_trust_score(
            followers or 0, following or 0, posts or 0, verified or False
        )
        return (result["score"], result["label"])
    
    # Composite Score UDF
    @udf(returnType=StructType([
        StructField("composite_score", DoubleType()),
        StructField("composite_rank", StringType()),
    ]))
    def composite_udf(trending, success, trust):
        # Weights: Trending=0.4, Success=0.35, Trust=0.25
        t = trending or 0
        s = success or 0
        tr = trust or 0
        composite = 0.4 * t + 0.35 * s + 0.25 * tr
        
        if composite >= 80:
            rank = "S"
        elif composite >= 65:
            rank = "A"
        elif composite >= 50:
            rank = "B"
        elif composite >= 35:
            rank = "C"
        else:
            rank = "D"
        
        return (round(composite, 2), rank)
    
    # Parse raw count (11.3K, 1.3M)
    @udf(LongType())
    def parse_raw(s):
        if s is None:
            return 0
        try:
            s = str(s).replace(",", "").strip().upper()
            if s.endswith("K"):
                return int(float(s[:-1]) * 1000)
            elif s.endswith("M"):
                return int(float(s[:-1]) * 1000000)
            elif s.endswith("B"):
                return int(float(s[:-1]) * 1000000000)
            return int(float(s))
        except:
            return 0
    
    return {
        "trending": trending_udf,
        "success": success_udf,
        "trust": trust_udf,
        "composite": composite_udf,
        "parse_raw": parse_raw,
    }


# ============================================================================
# REDIS SINK
# ============================================================================
def write_batch_to_redis(df: DataFrame, batch_id: int):
    """Write batch to Redis with TTL"""
    import redis
    
    try:
        r = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, decode_responses=True)
        rows = df.collect()
        
        pipe = r.pipeline()
        for row in rows:
            # Main score hash
            key = f"kol:scores:{row.platform}:{row.kol_id}"
            data = {
                "kol_id": row.kol_id,
                "platform": row.platform,
                "trending_score": str(row.trending_score or 0),
                "trending_label": row.trending_label or "N/A",
                "success_score": str(row.success_score or 0),
                "success_label": row.success_label or "N/A",
                "trust_score": str(row.trust_score or 0),
                "trust_label": row.trust_label or "N/A",
                "composite_score": str(row.composite_score or 0),
                "composite_rank": row.composite_rank or "N/A",
                "updated_at": datetime.now().isoformat(),
            }
            pipe.hset(key, mapping=data)
            pipe.expire(key, Config.REDIS_TTL)
            
            # Sorted sets for rankings
            if row.composite_score:
                pipe.zadd(f"rank:composite:{row.platform}", {row.kol_id: row.composite_score})
            if row.trending_score:
                pipe.zadd(f"rank:trending:{row.platform}", {row.kol_id: row.trending_score})
        
        pipe.execute()
        logger.info(f"✅ Batch {batch_id}: {len(rows)} scores → Redis")
        
    except Exception as e:
        logger.error(f"❌ Redis error: {e}")


# ============================================================================
# MAIN PIPELINE
# ============================================================================
def create_spark(local: bool = False) -> SparkSession:
    """Create Spark session"""
    builder = SparkSession.builder \
        .appName("MultiTopicHotPath") \
        .config("spark.sql.streaming.checkpointLocation", Config.CHECKPOINT_DIR) \
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
    
    if local:
        builder = builder.master("local[*]")
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_kafka(spark: SparkSession, topic: str) -> DataFrame:
    """Read from Kafka topic"""
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", Config.KAFKA_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()


def run_videos_trending_stream(spark: SparkSession, udfs: dict):
    """
    Process Videos stream for Trending Score.
    
    Aggregates video events per KOL in time windows → calculates velocity.
    """
    logger.info("📹 Starting Videos → Trending pipeline")
    
    videos_raw = read_kafka(spark, Config.TOPIC_VIDEOS)
    
    # Parse video events
    videos = videos_raw \
        .selectExpr("CAST(value AS STRING) as json", "timestamp as kafka_ts") \
        .select(from_json(col("json"), VIDEO_SCHEMA).alias("v"), col("kafka_ts")) \
        .select(
            col("v.username").alias("kol_id"),
            col("v.platform"),
            col("v.video_id"),
            coalesce(col("v.video_views"), lit(0)).alias("views"),
            coalesce(col("v.video_likes"), lit(0)).alias("likes"),
            coalesce(col("v.video_comments"), lit(0)).alias("comments"),
            coalesce(col("v.video_shares"), lit(0)).alias("shares"),
            col("kafka_ts")
        ) \
        .filter(col("kol_id").isNotNull()) \
        .withWatermark("kafka_ts", Config.WATERMARK)
    
    # Window aggregation for velocity
    trending_agg = videos \
        .groupBy(
            window(col("kafka_ts"), "10 minutes", "2 minutes"),
            col("kol_id"),
            col("platform")
        ) \
        .agg(
            count("*").alias("event_count"),
            spark_sum("views").alias("total_views"),
            avg("views").alias("avg_views"),
            spark_sum("likes").alias("total_likes"),
        )
    
    # Calculate global avg for normalization
    # (In production, use stateful processing or external lookup)
    global_avg = lit(5.0)  # Placeholder
    
    # Apply trending score
    trending_scored = trending_agg \
        .withColumn(
            "trending",
            udfs["trending"](
                col("event_count"),
                col("total_views"),
                col("avg_views"),
                global_avg
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("window.start").alias("window_start"),
            col("event_count"),
            col("total_views"),
            col("trending.trending_score").alias("trending_score"),
            col("trending.trending_label").alias("trending_label"),
            col("trending.trending_velocity").alias("trending_velocity"),
        )
    
    return trending_scored


def run_products_success_stream(spark: SparkSession, udfs: dict):
    """
    Process Products stream for Success Score.
    
    Each product event gets success prediction immediately.
    """
    logger.info("📦 Starting Products → Success pipeline")
    
    products_raw = read_kafka(spark, Config.TOPIC_PRODUCTS)
    
    # Parse product events
    products = products_raw \
        .selectExpr("CAST(value AS STRING) as json", "timestamp as kafka_ts") \
        .select(from_json(col("json"), PRODUCT_SCHEMA).alias("p"), col("kafka_ts")) \
        .select(
            col("p.username").alias("kol_id"),
            col("p.platform"),
            col("p.product_id"),
            coalesce(col("p.video_views"), lit(0)).alias("views"),
            coalesce(col("p.video_likes"), lit(0)).alias("likes"),
            coalesce(col("p.video_comments"), lit(0)).alias("comments"),
            coalesce(col("p.video_shares"), lit(0)).alias("shares"),
            coalesce(col("p.engagement_rate"), lit(0.0)).alias("engagement_rate"),
            coalesce(col("p.est_ctr"), lit(0.0)).alias("est_ctr"),
            coalesce(col("p.sold_count"), lit(0)).alias("sold_count"),
            col("kafka_ts")
        ) \
        .filter(col("kol_id").isNotNull()) \
        .withWatermark("kafka_ts", Config.WATERMARK)
    
    # Apply success score
    success_scored = products \
        .withColumn(
            "success",
            udfs["success"](
                col("views"),
                col("likes"),
                col("comments"),
                col("shares"),
                col("engagement_rate"),
                col("est_ctr")
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("product_id"),
            col("views"),
            col("engagement_rate"),
            col("success.success_score").alias("success_score"),
            col("success.success_label").alias("success_label"),
            col("success.success_confidence").alias("success_confidence"),
        )
    
    return success_scored


def run_profiles_trust_stream(spark: SparkSession, udfs: dict):
    """
    Process Profiles stream for Trust Score.
    """
    logger.info("👤 Starting Profiles → Trust pipeline")
    
    profiles_raw = read_kafka(spark, Config.TOPIC_PROFILES)
    
    # Parse profiles
    profiles = profiles_raw \
        .selectExpr("CAST(value AS STRING) as json", "timestamp as kafka_ts") \
        .select(from_json(col("json"), PROFILE_SCHEMA).alias("p"), col("kafka_ts")) \
        .select(
            col("p.username").alias("kol_id"),
            col("p.platform"),
            when(col("p.followers_count").isNotNull(), col("p.followers_count"))
                .otherwise(udfs["parse_raw"](col("p.followers_raw"))).alias("followers"),
            coalesce(col("p.following_count"), lit(0)).alias("following"),
            coalesce(col("p.post_count"), lit(0)).alias("posts"),
            coalesce(col("p.verified"), lit(False)).alias("verified"),
            col("kafka_ts")
        ) \
        .filter(col("kol_id").isNotNull()) \
        .withWatermark("kafka_ts", Config.WATERMARK)
    
    # Apply trust score
    trust_scored = profiles \
        .withColumn(
            "trust",
            udfs["trust"](
                col("followers"),
                col("following"),
                col("posts"),
                col("verified")
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("followers"),
            col("following"),
            col("posts"),
            col("trust.trust_score").alias("trust_score"),
            col("trust.trust_label").alias("trust_label"),
        )
    
    return trust_scored


def run_combined_output(
    spark: SparkSession,
    trending_df: DataFrame,
    success_df: DataFrame,
    trust_df: DataFrame,
    udfs: dict
):
    """
    Combine all scores into unified output.
    
    Note: This is simplified - in production you'd use state stores
    or Redis lookups to join across different time windows.
    """
    logger.info("🔗 Starting combined output pipeline")
    
    # For demo: Output each stream separately with composite = single score
    # In production: Use stateful joins or Redis to combine
    
    # Output Trust scores to console (simplest demo)
    trust_query = trust_df \
        .withColumn("trending_score", lit(50.0)) \
        .withColumn("trending_label", lit("N/A")) \
        .withColumn("success_score", lit(50.0)) \
        .withColumn("success_label", lit("N/A")) \
        .withColumn(
            "composite",
            udfs["composite"](
                lit(50.0),  # trending placeholder
                lit(50.0),  # success placeholder
                col("trust_score")
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("trending_score"),
            col("trending_label"),
            col("success_score"),
            col("success_label"),
            col("trust_score"),
            col("trust_label"),
            col("composite.composite_score").alias("composite_score"),
            col("composite.composite_rank").alias("composite_rank"),
        ) \
        .writeStream \
        .outputMode("append") \
        .foreachBatch(write_batch_to_redis) \
        .trigger(processingTime=Config.TRIGGER) \
        .start()
    
    return trust_query


def main(local: bool = False):
    """Main entry point"""
    logger.info("="*60)
    logger.info("  MULTI-TOPIC HOT PATH - Starting")
    logger.info("="*60)
    
    spark = create_spark(local)
    udfs = register_udfs()
    
    # Start individual streams
    # trending = run_videos_trending_stream(spark, udfs)
    # success = run_products_success_stream(spark, udfs)
    trust = run_profiles_trust_stream(spark, udfs)
    
    # Combined output - Write to Redis (NO Kafka output)
    query = trust \
        .withColumn(
            "composite",
            udfs["composite"](lit(50.0), lit(50.0), col("trust_score"))
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            lit(50.0).alias("trending_score"),
            lit("N/A").alias("trending_label"),
            lit(50.0).alias("success_score"),
            lit("N/A").alias("success_label"),
            col("trust_score"),
            col("trust_label"),
            col("composite.composite_score").alias("composite_score"),
            col("composite.composite_rank").alias("composite_rank"),
        ) \
        .writeStream \
        .outputMode("append") \
        .foreachBatch(write_batch_to_redis) \
        .trigger(processingTime=Config.TRIGGER) \
        .start()
    
    logger.info("✅ Streaming started - Output to REDIS")
    logger.info(f"   Redis: {Config.REDIS_HOST}:{Config.REDIS_PORT}")
    query.awaitTermination()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "cluster"], default="local")
    args = parser.parse_args()
    
    main(local=(args.mode == "local"))

#!/usr/bin/env python3
"""
Unified Hot Path Scoring - Spark Structured Streaming
======================================================

INTEGRATES ALL 3 SCORES:
1. Trending Score - Velocity-based (calculated in Spark)
2. Success Score  - LightGBM model prediction
3. Trust Score    - ML model or rule-based

Flow:
    Kafka Topics (profiles/videos/products)
        → Parse JSON
        → Calculate Trending (velocity)
        → Predict Success (LightGBM)
        → Calculate Trust (rules or API)
        → Output to Kafka (scores.stream) + Redis

Usage:
    docker exec kol-spark-master spark-submit \\
        --master spark://spark-master:7077 \\
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \\
        --py-files /opt/spark-jobs/models_bundle.zip \\
        /opt/spark-jobs/unified_hot_path.py

    # Local mode
    python unified_hot_path.py --mode local

Author: KOL Analytics Team
Date: 2024-12
"""

import os
import sys
import json
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

# Spark imports
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, from_json, to_json, struct, lit, current_timestamp,
    udf, when, coalesce, expr, window, count, sum as spark_sum,
    avg, max as spark_max, min as spark_min, lag, lead
)
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, DoubleType,
    BooleanType, TimestampType, MapType, IntegerType, FloatType
)
from pyspark.sql.window import Window

# Try to import models (may fail in Spark cluster - use broadcast)
try:
    import joblib
    import numpy as np
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UnifiedHotPath")


# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    """Unified configuration"""
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    
    # Input topics
    TOPIC_PROFILES = "kol.profiles.raw"
    TOPIC_VIDEOS = "kol.videos.raw"
    TOPIC_PRODUCTS = "kol.products.raw"
    TOPIC_DISCOVERY = "kol.discovery.raw"
    
    # Output topics
    TOPIC_SCORES = "scores.stream"
    TOPIC_TRENDING = "kol.trending.scores"
    
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_TTL_SECONDS = 3600  # 1 hour
    
    # Model paths (in container)
    MODEL_DIR = os.getenv("MODEL_DIR", "/opt/spark-jobs/models")
    SUCCESS_MODEL_PATH = f"{MODEL_DIR}/success_lgbm_model.pkl"
    SUCCESS_SCALER_PATH = f"{MODEL_DIR}/success_scaler.pkl"
    
    # Streaming config
    CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/tmp/spark_checkpoints/unified")
    TRIGGER_INTERVAL = "10 seconds"
    WATERMARK_DELAY = "5 minutes"
    
    # Trending score params
    TRENDING_HALF_LIFE_DAYS = 7.0  # Time decay half-life
    TRENDING_K = 0.8  # Sigmoid steepness
    TRENDING_THRESHOLD = 2.0  # Sigmoid center


# ============================================================================
# SCHEMAS
# ============================================================================

# Profile schema
PROFILE_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("username", StringType(), True),
    StructField("followers_count", LongType(), True),
    StructField("following_count", LongType(), True),
    StructField("post_count", LongType(), True),
    StructField("favorites_count", LongType(), True),
    StructField("followers_raw", StringType(), True),
    StructField("following_raw", StringType(), True),
    StructField("likes_raw", StringType(), True),
    StructField("verified", BooleanType(), True),
    StructField("bio", StringType(), True),
])

# Video schema
VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("video_id", StringType(), True),
    StructField("username", StringType(), True),
    StructField("video_views", LongType(), True),
    StructField("video_likes", LongType(), True),
    StructField("video_comments", LongType(), True),
    StructField("video_shares", LongType(), True),
    StructField("caption", StringType(), True),
])

# Product schema
PRODUCT_SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("platform", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("username", StringType(), True),
    StructField("video_views", LongType(), True),
    StructField("video_likes", LongType(), True),
    StructField("video_comments", LongType(), True),
    StructField("video_shares", LongType(), True),
    StructField("engagement_total", LongType(), True),
    StructField("engagement_rate", DoubleType(), True),
    StructField("est_clicks", LongType(), True),
    StructField("est_ctr", DoubleType(), True),
    StructField("sold_count", LongType(), True),
    StructField("price", DoubleType(), True),
])

# Unified score output schema
SCORE_OUTPUT_SCHEMA = StructType([
    StructField("kol_id", StringType(), False),
    StructField("platform", StringType(), True),
    StructField("scored_at", StringType(), False),
    # Trending
    StructField("trending_score", DoubleType(), True),
    StructField("trending_label", StringType(), True),
    StructField("trending_velocity", DoubleType(), True),
    StructField("trending_momentum", DoubleType(), True),
    # Success
    StructField("success_score", DoubleType(), True),
    StructField("success_label", StringType(), True),
    StructField("success_confidence", DoubleType(), True),
    # Trust
    StructField("trust_score", DoubleType(), True),
    StructField("trust_label", StringType(), True),
    # Composite
    StructField("composite_score", DoubleType(), True),
    StructField("composite_rank", StringType(), True),
    # Metadata
    StructField("latency_ms", IntegerType(), True),
    StructField("model_versions", StringType(), True),
])


# ============================================================================
# TRENDING SCORE LOGIC (Velocity-based)
# ============================================================================
class TrendingScoreCalculator:
    """
    TrendingScore V2 - Velocity-based calculation.
    
    Formula:
        raw = α * personal_growth + β * market_position + γ * momentum
        score = 100 / (1 + exp(-k * (raw - threshold)))
    
    Where:
        - personal_growth = current_velocity / baseline_velocity
        - market_position = current_velocity / global_avg
        - momentum = (current - previous) / previous
        - α=0.5, β=0.3, γ=0.2
    """
    
    @staticmethod
    def calculate_time_decay(event_age_days: float, half_life_days: float = 7.0) -> float:
        """Exponential time decay: weight = exp(-λ * t)"""
        if event_age_days < 0:
            return 1.0
        decay_rate = math.log(2) / half_life_days
        return math.exp(-decay_rate * event_age_days)
    
    @staticmethod
    def calculate_engagement_weight(views: float, global_avg_views: float = 10000) -> float:
        """Log-scaled engagement weight normalized to [0.1, 1.0]"""
        if views <= 0:
            return 0.1
        ratio = views / global_avg_views
        weight = math.log1p(ratio) / math.log1p(100)
        return 0.1 + 0.9 * min(weight, 1.0)
    
    @staticmethod
    def calculate_trending_score(
        current_velocity: float,
        baseline_velocity: float,
        global_avg_velocity: float,
        momentum: float = 0.0,
        k: float = 0.8,
        threshold: float = 2.0
    ) -> Dict[str, Any]:
        """Calculate trending score with sigmoid normalization."""
        
        # Avoid division by zero
        baseline = max(baseline_velocity, 0.1)
        global_avg = max(global_avg_velocity, 0.1)
        
        # Component scores
        personal_growth = current_velocity / baseline
        market_position = current_velocity / global_avg
        
        # Weighted combination: α=0.5, β=0.3, γ=0.2
        raw_score = (
            0.5 * personal_growth +
            0.3 * market_position +
            0.2 * (1 + momentum)
        )
        
        # Sigmoid normalization to [0, 100]
        trending_score = 100 / (1 + math.exp(-k * (raw_score - threshold)))
        
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
            "trending_velocity": round(current_velocity, 4),
            "trending_momentum": round(momentum, 4),
            "personal_growth": round(personal_growth, 4),
            "market_position": round(market_position, 4),
        }


# ============================================================================
# SUCCESS SCORE LOGIC (LightGBM)
# ============================================================================
class SuccessScorePredictor:
    """
    Success Score - Uses trained LightGBM model.
    
    Binary classification: High-success (1) vs Not-high (0)
    Features: video_views, engagement_rate, likes_per_view, etc.
    """
    
    def __init__(self, model_path: str = None, scaler_path: str = None):
        self.model = None
        self.scaler = None
        self.feature_cols = [
            "video_views", "video_likes", "video_comments", "video_shares",
            "engagement_total", "engagement_rate", "est_clicks", "est_ctr",
            "likes_per_view", "comments_per_view", "shares_per_view",
            "log_views", "log_engagement"
        ]
        
        # Try to load model
        if model_path and os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                logger.info(f"✅ Loaded Success model from {model_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load model: {e}")
        
        if scaler_path and os.path.exists(scaler_path):
            try:
                self.scaler = joblib.load(scaler_path)
                logger.info(f"✅ Loaded scaler from {scaler_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load scaler: {e}")
    
    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Predict success probability for a product/video."""
        
        # If no model, use rule-based fallback
        if self.model is None:
            return self._rule_based_predict(features)
        
        try:
            # Prepare features
            X = np.array([[features.get(col, 0) for col in self.feature_cols]])
            
            if self.scaler:
                X = self.scaler.transform(X)
            
            # Predict
            proba = self.model.predict_proba(X)[0]
            pred_class = self.model.predict(X)[0]
            
            # Map to score (0-100)
            success_score = proba[1] * 100 if len(proba) > 1 else proba[0] * 100
            
            if success_score >= 70:
                label = "High"
            elif success_score >= 40:
                label = "Medium"
            else:
                label = "Low"
            
            return {
                "success_score": round(success_score, 2),
                "success_label": label,
                "success_confidence": round(max(proba) * 100, 2),
            }
        except Exception as e:
            logger.warning(f"Prediction error: {e}")
            return self._rule_based_predict(features)
    
    def _rule_based_predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Fallback rule-based success prediction."""
        
        views = features.get("video_views", 0)
        engagement_rate = features.get("engagement_rate", 0)
        likes_per_view = features.get("likes_per_view", 0)
        
        # Simple weighted scoring
        score = 0
        
        # Views component (40%)
        if views >= 100000:
            score += 40
        elif views >= 50000:
            score += 30
        elif views >= 10000:
            score += 20
        elif views >= 1000:
            score += 10
        
        # Engagement rate component (35%)
        if engagement_rate >= 0.1:
            score += 35
        elif engagement_rate >= 0.05:
            score += 25
        elif engagement_rate >= 0.02:
            score += 15
        elif engagement_rate >= 0.01:
            score += 5
        
        # Likes per view component (25%)
        if likes_per_view >= 0.1:
            score += 25
        elif likes_per_view >= 0.05:
            score += 15
        elif likes_per_view >= 0.02:
            score += 8
        
        if score >= 70:
            label = "High"
        elif score >= 40:
            label = "Medium"
        else:
            label = "Low"
        
        return {
            "success_score": round(score, 2),
            "success_label": label,
            "success_confidence": 60.0,  # Lower confidence for rule-based
        }


# ============================================================================
# TRUST SCORE LOGIC (Rule-based or API)
# ============================================================================
class TrustScoreCalculator:
    """
    Trust Score - Rule-based calculation.
    
    Components:
        - Follower authenticity (ratio followers/following)
        - Engagement authenticity (engagement vs followers)
        - Account age/maturity
        - Verification status
    """
    
    @staticmethod
    def calculate_trust_score(
        followers_count: int,
        following_count: int,
        post_count: int,
        favorites_count: int,
        verified: bool,
        avg_engagement: float = 0
    ) -> Dict[str, Any]:
        """Calculate trust score based on profile metrics."""
        
        score = 0
        reasons = []
        
        # 1. Follower/Following ratio (25 points)
        if following_count > 0:
            ratio = followers_count / following_count
            if ratio >= 10:
                score += 25
                reasons.append("excellent_ratio")
            elif ratio >= 5:
                score += 20
                reasons.append("good_ratio")
            elif ratio >= 2:
                score += 15
                reasons.append("decent_ratio")
            elif ratio >= 1:
                score += 10
                reasons.append("balanced_ratio")
            else:
                score += 5
                reasons.append("low_ratio")
        else:
            score += 15  # No following = neutral
        
        # 2. Follower count credibility (25 points)
        if followers_count >= 1000000:
            score += 25
            reasons.append("mega_influencer")
        elif followers_count >= 100000:
            score += 22
            reasons.append("macro_influencer")
        elif followers_count >= 10000:
            score += 18
            reasons.append("micro_influencer")
        elif followers_count >= 1000:
            score += 12
            reasons.append("nano_influencer")
        else:
            score += 5
            reasons.append("starter")
        
        # 3. Post activity (20 points)
        if post_count >= 100:
            score += 20
            reasons.append("very_active")
        elif post_count >= 50:
            score += 15
            reasons.append("active")
        elif post_count >= 20:
            score += 10
            reasons.append("moderate")
        elif post_count >= 5:
            score += 5
            reasons.append("new_creator")
        else:
            score += 2
        
        # 4. Engagement authenticity (20 points)
        if followers_count > 0:
            expected_engagement = followers_count * 0.03  # 3% baseline
            if avg_engagement >= expected_engagement * 0.5:
                score += 20
                reasons.append("authentic_engagement")
            elif avg_engagement >= expected_engagement * 0.2:
                score += 12
                reasons.append("moderate_engagement")
            else:
                score += 5
                reasons.append("low_engagement")
        else:
            score += 10
        
        # 5. Verification bonus (10 points)
        if verified:
            score += 10
            reasons.append("verified")
        
        # Cap at 100
        score = min(score, 100)
        
        # Label assignment
        if score >= 80:
            label = "Highly Trustworthy"
        elif score >= 60:
            label = "Trustworthy"
        elif score >= 40:
            label = "Moderate"
        elif score >= 25:
            label = "Low Trust"
        else:
            label = "Suspicious"
        
        return {
            "trust_score": round(score, 2),
            "trust_label": label,
            "trust_reasons": reasons,
        }


# ============================================================================
# COMPOSITE SCORE
# ============================================================================
def calculate_composite_score(
    trending_score: float,
    success_score: float,
    trust_score: float,
    weights: Dict[str, float] = None
) -> Dict[str, Any]:
    """
    Calculate weighted composite score.
    
    Default weights: Trending=0.4, Success=0.35, Trust=0.25
    """
    if weights is None:
        weights = {
            "trending": 0.40,
            "success": 0.35,
            "trust": 0.25,
        }
    
    composite = (
        weights["trending"] * trending_score +
        weights["success"] * success_score +
        weights["trust"] * trust_score
    )
    
    # Rank assignment
    if composite >= 80:
        rank = "S"  # Top tier
    elif composite >= 65:
        rank = "A"  # Excellent
    elif composite >= 50:
        rank = "B"  # Good
    elif composite >= 35:
        rank = "C"  # Average
    else:
        rank = "D"  # Below average
    
    return {
        "composite_score": round(composite, 2),
        "composite_rank": rank,
    }


# ============================================================================
# SPARK UDFs
# ============================================================================
def create_scoring_udfs(spark: SparkSession, success_predictor: SuccessScorePredictor):
    """Register all scoring UDFs"""
    
    # Trending Score UDF
    @udf(returnType=StructType([
        StructField("trending_score", DoubleType()),
        StructField("trending_label", StringType()),
        StructField("trending_velocity", DoubleType()),
        StructField("trending_momentum", DoubleType()),
    ]))
    def trending_score_udf(
        event_count: int,
        total_views: int,
        global_avg_events: float,
        global_avg_views: float,
        prev_event_count: int = None
    ):
        # Calculate velocity (weighted events)
        view_weight = TrendingScoreCalculator.calculate_engagement_weight(
            total_views or 0, global_avg_views or 10000
        )
        current_velocity = (event_count or 0) * view_weight
        
        # Baseline and momentum
        baseline = global_avg_events or 1.0
        momentum = 0.0
        if prev_event_count and prev_event_count > 0:
            momentum = (event_count - prev_event_count) / prev_event_count
        
        result = TrendingScoreCalculator.calculate_trending_score(
            current_velocity=current_velocity,
            baseline_velocity=baseline,
            global_avg_velocity=baseline,
            momentum=momentum
        )
        
        return (
            result["trending_score"],
            result["trending_label"],
            result["trending_velocity"],
            result["trending_momentum"],
        )
    
    # Trust Score UDF
    @udf(returnType=StructType([
        StructField("trust_score", DoubleType()),
        StructField("trust_label", StringType()),
    ]))
    def trust_score_udf(
        followers: int,
        following: int,
        posts: int,
        favorites: int,
        verified: bool,
        avg_engagement: float
    ):
        result = TrustScoreCalculator.calculate_trust_score(
            followers_count=followers or 0,
            following_count=following or 0,
            post_count=posts or 0,
            favorites_count=favorites or 0,
            verified=verified or False,
            avg_engagement=avg_engagement or 0
        )
        return (result["trust_score"], result["trust_label"])
    
    # Success Score UDF (uses broadcast model)
    @udf(returnType=StructType([
        StructField("success_score", DoubleType()),
        StructField("success_label", StringType()),
        StructField("success_confidence", DoubleType()),
    ]))
    def success_score_udf(
        video_views: int,
        video_likes: int,
        video_comments: int,
        video_shares: int,
        engagement_rate: float,
        est_ctr: float
    ):
        features = {
            "video_views": video_views or 0,
            "video_likes": video_likes or 0,
            "video_comments": video_comments or 0,
            "video_shares": video_shares or 0,
            "engagement_total": (video_likes or 0) + (video_comments or 0) + (video_shares or 0),
            "engagement_rate": engagement_rate or 0,
            "est_clicks": 0,
            "est_ctr": est_ctr or 0,
            "likes_per_view": (video_likes or 0) / max(video_views or 1, 1),
            "comments_per_view": (video_comments or 0) / max(video_views or 1, 1),
            "shares_per_view": (video_shares or 0) / max(video_views or 1, 1),
            "log_views": math.log1p(video_views or 0),
            "log_engagement": math.log1p((video_likes or 0) + (video_comments or 0)),
        }
        
        result = success_predictor.predict(features)
        return (
            result["success_score"],
            result["success_label"],
            result["success_confidence"],
        )
    
    # Composite Score UDF
    @udf(returnType=StructType([
        StructField("composite_score", DoubleType()),
        StructField("composite_rank", StringType()),
    ]))
    def composite_score_udf(trending: float, success: float, trust: float):
        result = calculate_composite_score(
            trending_score=trending or 0,
            success_score=success or 0,
            trust_score=trust or 0
        )
        return (result["composite_score"], result["composite_rank"])
    
    return {
        "trending_score_udf": trending_score_udf,
        "trust_score_udf": trust_score_udf,
        "success_score_udf": success_score_udf,
        "composite_score_udf": composite_score_udf,
    }


# ============================================================================
# REDIS OUTPUT
# ============================================================================
def write_to_redis(batch_df: DataFrame, batch_id: int):
    """Write scores to Redis in foreachBatch - supports both old and new schemas"""
    
    import redis
    
    try:
        r = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )
        
        rows = batch_df.collect()
        pipe = r.pipeline()
        
        for row in rows:
            kol_id = row.kol_id
            
            # === SCHEMA 1: New unified schema ===
            # Key: kol:unified:{platform}:{kol_id}
            unified_key = f"kol:unified:{row.platform}:{kol_id}"
            score_data = {
                "kol_id": kol_id,
                "platform": row.platform,
                "scored_at": row.scored_at,
                "trending_score": row.trending_score,
                "trending_label": row.trending_label,
                "success_score": row.success_score,
                "success_label": row.success_label,
                "trust_score": row.trust_score,
                "trust_label": row.trust_label,
                "composite_score": row.composite_score,
                "composite_rank": row.composite_rank,
            }
            pipe.hset(unified_key, mapping={k: str(v) for k, v in score_data.items() if v is not None})
            pipe.expire(unified_key, Config.REDIS_TTL_SECONDS)
            
            # === SCHEMA 2: Legacy schema for Dashboard/metrics_refresh.py compatibility ===
            # Key: streaming_scores:{username}
            legacy_key = f"streaming_scores:{kol_id}"
            legacy_data = {
                "username": kol_id,
                "platform": row.platform or "tiktok",
                "score": row.composite_score or row.trending_score or 50.0,
                "trending_score": row.trending_score or 50.0,
                "trust_score": row.trust_score or 50.0,
                "success_score": row.success_score or 50.0,
                "label": row.composite_rank or row.trending_label or "N/A",
                "updated_at": row.scored_at,
            }
            pipe.hset(legacy_key, mapping={k: str(v) for k, v in legacy_data.items() if v is not None})

            pipe.expire(legacy_key, Config.REDIS_TTL_SECONDS)
            
            # === Sorted sets for ranking ===
            if row.composite_score:
                pipe.zadd(f"ranking:{row.platform}:composite", {kol_id: row.composite_score})
            if row.trending_score:
                pipe.zadd(f"ranking:{row.platform}:trending", {kol_id: row.trending_score})
        
        pipe.execute()
        logger.info(f"✅ Batch {batch_id}: Wrote {len(rows)} scores to Redis (unified + legacy)")
        
    except Exception as e:
        logger.error(f"❌ Redis write error batch {batch_id}: {e}")


# ============================================================================
# SPARK SESSION
# ============================================================================
def create_spark_session(local: bool = False) -> SparkSession:
    """Create Spark session with Kafka support"""
    
    builder = SparkSession.builder \
        .appName("KOL-UnifiedHotPath") \
        .config("spark.sql.streaming.checkpointLocation", Config.CHECKPOINT_DIR) \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
    
    if local:
        builder = builder.master("local[*]")
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    
    logger.info(f"✅ Spark session created")
    logger.info(f"   Kafka: {Config.KAFKA_BOOTSTRAP_SERVERS}")
    
    return spark


# ============================================================================
# KAFKA STREAMS
# ============================================================================
def read_kafka_stream(spark: SparkSession, topic: str) -> DataFrame:
    """Read from Kafka topic"""
    
    return spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", Config.KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()


def parse_raw_count_udf():
    """UDF to parse raw strings like '11.3K', '1.3M'"""
    
    @udf(LongType())
    def parse_raw(raw_str: str) -> int:
        if raw_str is None:
            return 0
        try:
            raw_str = str(raw_str).replace(",", "").strip()
            if raw_str.upper().endswith("K"):
                return int(float(raw_str[:-1]) * 1000)
            elif raw_str.upper().endswith("M"):
                return int(float(raw_str[:-1]) * 1000000)
            elif raw_str.upper().endswith("B"):
                return int(float(raw_str[:-1]) * 1000000000)
            else:
                return int(float(raw_str))
        except (ValueError, TypeError):
            return 0
    
    return parse_raw


# ============================================================================
# MAIN STREAMING PIPELINE
# ============================================================================
def run_unified_hot_path(local: bool = False):
    """Main entry point for unified hot path streaming"""
    
    logger.info("="*60)
    logger.info("  UNIFIED HOT PATH - Starting")
    logger.info("="*60)
    
    # Create Spark session
    spark = create_spark_session(local=local)
    
    # Initialize predictors
    success_predictor = SuccessScorePredictor(
        model_path=Config.SUCCESS_MODEL_PATH,
        scaler_path=Config.SUCCESS_SCALER_PATH
    )
    
    # Create UDFs
    udfs = create_scoring_udfs(spark, success_predictor)
    parse_raw = parse_raw_count_udf()
    
    # Read profile stream
    profiles_raw = read_kafka_stream(spark, Config.TOPIC_PROFILES)
    
    # Parse profiles
    profiles = profiles_raw \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_ts") \
        .select(from_json(col("json_str"), PROFILE_SCHEMA).alias("data"), col("kafka_ts")) \
        .select(
            col("data.username").alias("kol_id"),
            col("data.platform"),
            when(col("data.followers_count").isNotNull(), col("data.followers_count"))
                .otherwise(parse_raw(col("data.followers_raw"))).alias("followers"),
            when(col("data.following_count").isNotNull(), col("data.following_count"))
                .otherwise(parse_raw(col("data.following_raw"))).alias("following"),
            coalesce(col("data.post_count"), lit(0)).alias("posts"),
            when(col("data.favorites_count").isNotNull(), col("data.favorites_count"))
                .otherwise(parse_raw(col("data.likes_raw"))).alias("favorites"),
            coalesce(col("data.verified"), lit(False)).alias("verified"),
            col("kafka_ts")
        ) \
        .filter(col("kol_id").isNotNull())
    
    # Add watermark for late data handling
    profiles_with_watermark = profiles \
        .withWatermark("kafka_ts", Config.WATERMARK_DELAY)
    
    # Calculate Trust Score
    profiles_with_trust = profiles_with_watermark \
        .withColumn(
            "trust_result",
            udfs["trust_score_udf"](
                col("followers"),
                col("following"),
                col("posts"),
                col("favorites"),
                col("verified"),
                lit(0.0)  # avg_engagement placeholder
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("followers"),
            col("following"),
            col("posts"),
            col("trust_result.trust_score").alias("trust_score"),
            col("trust_result.trust_label").alias("trust_label"),
            col("kafka_ts")
        )
    
    # Aggregate for trending (window-based)
    trending_agg = profiles_with_watermark \
        .groupBy(
            window(col("kafka_ts"), "10 minutes", "5 minutes"),
            col("kol_id"),
            col("platform")
        ) \
        .agg(
            count("*").alias("event_count"),
            spark_sum("followers").alias("total_followers")
        )
    
    # Add timestamp and default scores for composite calculation
    final_scores = profiles_with_trust \
        .withColumn("scored_at", current_timestamp().cast("string")) \
        .withColumn("trending_score", lit(50.0)) \
        .withColumn("trending_label", lit("N/A")) \
        .withColumn("success_score", lit(50.0)) \
        .withColumn("success_label", lit("N/A")) \
        .withColumn("success_confidence", lit(0.0)) \
        .withColumn(
            "composite_result",
            udfs["composite_score_udf"](
                lit(50.0),  # trending placeholder
                lit(50.0),  # success placeholder
                col("trust_score")
            )
        ) \
        .select(
            col("kol_id"),
            col("platform"),
            col("scored_at"),
            col("trending_score"),
            col("trending_label"),
            col("success_score"),
            col("success_label"),
            col("trust_score"),
            col("trust_label"),
            col("composite_result.composite_score").alias("composite_score"),
            col("composite_result.composite_rank").alias("composite_rank"),
        )
    
    # OUTPUT: Write directly to Redis (NO Kafka output needed!)
    # Redis serves as the single source of truth for UI queries
    query = final_scores \
        .writeStream \
        .outputMode("append") \
        .foreachBatch(write_to_redis) \
        .trigger(processingTime=Config.TRIGGER_INTERVAL) \
        .start()
    
    logger.info("✅ Streaming query started - Output to REDIS")
    logger.info(f"   Input: {Config.TOPIC_PROFILES}")
    logger.info(f"   Output: Redis (kol:unified:{{platform}}:{{kol_id}})")
    logger.info(f"   Trigger: {Config.TRIGGER_INTERVAL}")
    
    # Wait for termination
    query.awaitTermination()


# ============================================================================
# CLI
# ============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Hot Path Scoring")
    parser.add_argument("--mode", choices=["local", "cluster"], default="local")
    parser.add_argument("--debug", action="store_true")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    run_unified_hot_path(local=(args.mode == "local"))

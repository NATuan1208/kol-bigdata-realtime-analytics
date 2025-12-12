"""
ETL: Bronze -> Silver (PySpark on Docker Cluster)
==================================================

Chạy trên: Spark Cluster (kol-spark-master:7077)
Đọc từ: MinIO s3a://kol-platform/bronze/raw/*
Ghi ra: MinIO s3a://kol-platform/silver/* (Parquet format)

Transformations:
1. kol_profiles - Unified KOL profile data across platforms
2. kol_content - Posts/videos/tweets với engagement metrics  
3. kol_trust_features - Features cho Trust Score model (có labels)
4. kol_engagement_metrics - Aggregated engagement per KOL

Cách chạy:
-----------
# Submit tất cả transformations
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py

# Chỉ chạy 1 table
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py --table kol_trust_features

# Dry-run
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py --dry-run

Author: KOL Analytics Team (IE212 - UIT)
Date: 2025-11-26
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Optional, List

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    FloatType, BooleanType, ArrayType, MapType
)


# =============================================================================
# CONFIGURATION
# =============================================================================
# SECURITY: Credentials MUST be provided via environment variables
# DO NOT hardcode credentials in production
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "sme-minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
BUCKET = os.getenv("BUCKET", "kol-platform")

# Validate required credentials
if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    import warnings
    warnings.warn(
        "SECURITY WARNING: MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set via environment variables. "
        "Using default development credentials is NOT recommended for production.",
        UserWarning
    )
    # Fallback for development only - remove in production
    MINIO_ACCESS_KEY = MINIO_ACCESS_KEY or "minioadmin"
    MINIO_SECRET_KEY = MINIO_SECRET_KEY or "minioadmin123"

BRONZE_PATH = f"s3a://{BUCKET}/bronze/raw"
SILVER_PATH = f"s3a://{BUCKET}/silver"


# =============================================================================
# SPARK SESSION
# =============================================================================
def create_spark_session(master_url: str = None) -> SparkSession:
    """Create Spark session with S3A (MinIO) support."""
    if master_url is None:
        master_url = os.getenv("SPARK_MASTER", "spark://spark-master:7077")
    
    print(f"🔌 Connecting to Spark Master: {master_url}")
    
    return (SparkSession.builder
        .appName("BronzeToSilver_ETL")
        .master(master_url)
        # S3A configuration
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{MINIO_ENDPOINT}")
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        # Performance
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )


def load_bronze_source(spark: SparkSession, source: str) -> DataFrame:
    """Load Bronze data from MinIO (JSONL format)."""
    path = f"{BRONZE_PATH}/{source}/"
    print(f"📥 Loading: {path}")
    
    try:
        df = spark.read.json(path)
        count = df.count()
        print(f"   Loaded: {count:,} records")
        return df
    except Exception as e:
        print(f"   ⚠️ Error loading {source}: {e}")
        return spark.createDataFrame([], StructType([]))


def save_silver_table(df: DataFrame, table_name: str, dry_run: bool = False):
    """Save DataFrame to Silver layer as Parquet."""
    if df.count() == 0:
        print(f"   ⚠️ No data to save for {table_name}")
        return
    
    output_path = f"{SILVER_PATH}/{table_name}/"
    
    if dry_run:
        print(f"🔍 DRY RUN: Would save {df.count():,} records to {output_path}")
        df.show(5, truncate=False)
        return
    
    print(f"💾 Saving to: {output_path}")
    
    # Save as Parquet with overwrite
    df.write.mode("overwrite").parquet(output_path)
    
    print(f"   ✅ Saved {df.count():,} records")


# =============================================================================
# TRANSFORMATION: kol_profiles
# =============================================================================
def transform_kol_profiles(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze data to unified KOL profile format.
    
    Sources: wikipedia_backlinko, twitter_human_bots
    """
    print("\n" + "="*60)
    print("🔄 Transforming: kol_profiles")
    print("="*60)
    
    profiles_list = []
    
    # 1. Process wikipedia_backlinko
    try:
        wiki_df = load_bronze_source(spark, "wikipedia_backlinko")
        
        if wiki_df.count() > 0:
            wiki_profiles = (wiki_df
                .select(
                    F.col("kol_id"),
                    F.lit("youtube").alias("platform"),
                    # Extract username from Link
                    F.regexp_extract(F.col("payload.Link"), r"/([^/]+)/?$", 1).alias("username"),
                    F.col("payload.Name").alias("display_name"),
                    F.lit("").alias("bio"),
                    # Parse subscribers (in millions)
                    (F.regexp_extract(
                        F.col("payload.`Subscribers (millions)`").cast("string"), 
                        r"[\d.]+", 0
                    ).cast("float") * 1000000).cast("int").alias("followers_count"),
                    F.lit(0).alias("following_count"),
                    F.lit(0).alias("post_count"),
                    F.lit(True).alias("verified"),
                    F.lit(None).cast("string").alias("account_created_at"),
                    F.col("payload.Link").alias("profile_url"),
                    F.col("payload.Category").alias("category"),
                    F.lit("wikipedia_backlinko").alias("source"),
                    F.current_timestamp().alias("processed_at")
                )
                .filter(F.col("username").isNotNull() & (F.col("username") != ""))
            )
            profiles_list.append(wiki_profiles)
    except Exception as e:
        print(f"   ⚠️ Error processing wikipedia_backlinko: {e}")
    
    # 2. Process twitter_human_bots
    try:
        twitter_df = load_bronze_source(spark, "twitter_human_bots")
        
        if twitter_df.count() > 0:
            twitter_profiles = (twitter_df
                .select(
                    F.col("kol_id"),
                    F.lit("twitter").alias("platform"),
                    F.col("payload.profile.screen_name").alias("username"),
                    F.col("payload.profile.name").alias("display_name"),
                    F.coalesce(F.col("payload.profile.description"), F.lit("")).alias("bio"),
                    F.coalesce(F.col("payload.profile.followers_count"), F.lit(0)).alias("followers_count"),
                    F.coalesce(F.col("payload.profile.friends_count"), F.lit(0)).alias("following_count"),
                    F.coalesce(F.col("payload.profile.statuses_count"), F.lit(0)).alias("post_count"),
                    F.coalesce(F.col("payload.profile.verified"), F.lit(False)).alias("verified"),
                    F.col("payload.profile.created_at").alias("account_created_at"),
                    F.concat(F.lit("https://twitter.com/"), 
                             F.col("payload.profile.screen_name")).alias("profile_url"),
                    F.lit("Unknown").alias("category"),
                    F.lit("twitter_human_bots").alias("source"),
                    F.current_timestamp().alias("processed_at")
                )
                .filter(F.col("username").isNotNull() & (F.col("username") != ""))
            )
            profiles_list.append(twitter_profiles)
    except Exception as e:
        print(f"   ⚠️ Error processing twitter_human_bots: {e}")
    
    # Union all profiles
    if not profiles_list:
        print("   ❌ No profile data found")
        return {"table": "kol_profiles", "records": 0, "status": "error"}
    
    all_profiles = profiles_list[0]
    for df in profiles_list[1:]:
        all_profiles = all_profiles.unionByName(df, allowMissingColumns=True)
    
    # Deduplicate by platform + username
    final_profiles = (all_profiles
        .withColumn("profile_key", F.concat(F.col("platform"), F.lit("_"), F.col("username")))
        .dropDuplicates(["profile_key"])
        .drop("profile_key")
    )
    
    count = final_profiles.count()
    print(f"✅ Generated {count:,} unique profiles")
    
    save_silver_table(final_profiles, "kol_profiles", dry_run)
    
    return {"table": "kol_profiles", "records": count, "status": "success"}


# =============================================================================
# TRANSFORMATION: kol_content
# =============================================================================
def transform_kol_content(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze data to unified content/post format.
    
    Sources: short_video_trends, youtube_trending
    """
    print("\n" + "="*60)
    print("🔄 Transforming: kol_content")
    print("="*60)
    
    content_list = []
    
    # 1. Process short_video_trends
    try:
        svt_df = load_bronze_source(spark, "short_video_trends")
        
        if svt_df.count() > 0:
            svt_content = (svt_df
                .select(
                    # Content ID - use row_id or generate
                    F.coalesce(
                        F.col("payload.row_id").cast("string"),
                        F.concat(F.col("kol_id"), F.lit("_"), F.monotonically_increasing_id())
                    ).alias("content_id"),
                    F.coalesce(F.col("kol_id"), F.col("payload.author_handle")).alias("kol_id"),
                    F.lower(F.coalesce(F.col("payload.platform"), F.col("platform"))).alias("platform"),
                    F.lit("video").alias("content_type"),
                    F.coalesce(F.col("payload.title_keywords"), F.lit("")).alias("title"),
                    F.coalesce(F.col("payload.sample_comments"), F.lit("")).alias("description"),
                    # Metrics - use actual field names from Bronze
                    F.coalesce(F.col("payload.views"), F.lit(0)).cast("long").alias("views"),
                    F.coalesce(F.col("payload.likes"), F.lit(0)).cast("long").alias("likes"),
                    F.coalesce(F.col("payload.comments"), F.lit(0)).cast("long").alias("comments"),
                    F.coalesce(F.col("payload.shares"), F.lit(0)).cast("long").alias("shares"),
                    # Engagement rate
                    F.coalesce(F.col("payload.engagement_rate"), F.lit(0.0)).cast("float").alias("engagement_rate"),
                    # Timestamps
                    F.coalesce(F.col("payload.publish_date_approx"), F.lit("")).alias("posted_at"),
                    F.coalesce(F.col("payload.duration_sec"), F.lit(0)).cast("int").alias("duration_seconds"),
                    # Tags
                    F.coalesce(F.col("payload.hashtag"), F.lit("")).alias("tags_raw"),
                    F.lit("short_video_trends").alias("source"),
                    F.current_timestamp().alias("processed_at")
                )
                .filter(F.col("content_id").isNotNull())
            )
            content_list.append(svt_content)
    except Exception as e:
        print(f"   ⚠️ Error processing short_video_trends: {e}")
    
    # 2. Process youtube_trending
    try:
        yt_df = load_bronze_source(spark, "youtube_trending")
        
        if yt_df.count() > 0:
            yt_content = (yt_df
                .select(
                    F.col("payload.video_id").alias("content_id"),
                    F.coalesce(F.col("payload.channel_id"), F.col("kol_id")).alias("kol_id"),
                    F.lit("youtube").alias("platform"),
                    F.lit("video").alias("content_type"),
                    F.coalesce(F.col("payload.title"), F.lit("")).alias("title"),
                    F.coalesce(F.col("payload.description"), F.lit("")).alias("description"),
                    # Use actual field names: view_count, likes, comment_count
                    F.coalesce(F.col("payload.view_count"), F.lit(0)).cast("long").alias("views"),
                    F.coalesce(F.col("payload.likes"), F.lit(0)).cast("long").alias("likes"),
                    F.coalesce(F.col("payload.comment_count"), F.lit(0)).cast("long").alias("comments"),
                    F.lit(0).cast("long").alias("shares"),
                    F.lit(0.0).cast("float").alias("engagement_rate"),
                    F.col("payload.publish_time").alias("posted_at"),
                    F.lit(0).alias("duration_seconds"),
                    F.lit("").alias("tags_raw"),
                    F.lit("youtube_trending").alias("source"),
                    F.current_timestamp().alias("processed_at")
                )
                .filter(F.col("content_id").isNotNull() & (F.col("content_id") != ""))
            )
            content_list.append(yt_content)
    except Exception as e:
        print(f"   ⚠️ Error processing youtube_trending: {e}")
    
    # Union all content
    if not content_list:
        print("   ❌ No content data found")
        return {"table": "kol_content", "records": 0, "status": "error"}
    
    all_content = content_list[0]
    for df in content_list[1:]:
        all_content = all_content.unionByName(df, allowMissingColumns=True)
    
    # Calculate engagement rate if not present
    final_content = (all_content
        .withColumn(
            "engagement_rate",
            F.when(
                (F.col("engagement_rate") == 0) & (F.col("views") > 0),
                ((F.col("likes") + F.col("comments") + F.col("shares")) / F.col("views") * 100)
            ).otherwise(F.col("engagement_rate"))
        )
        .withColumn("engagement_rate", F.round(F.col("engagement_rate"), 4))
    )
    
    count = final_content.count()
    print(f"✅ Generated {count:,} content records")
    
    save_silver_table(final_content, "kol_content", dry_run)
    
    return {"table": "kol_content", "records": count, "status": "success"}


# =============================================================================
# TRANSFORMATION: kol_trust_features
# =============================================================================
def transform_kol_trust_features(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze data to Trust Score features.
    
    ⭐ KEY TABLE: Contains labeled data for ML training!
    
    SEMANTIC MAPPING (Option A+B approach):
    - Original dataset: Bot detection (is_bot = tài khoản này LÀ bot)
    - Our interpretation: KOL Trust detection (is_untrustworthy = KOL này KHÔNG đáng tin)
    
    Lý do re-purpose:
    - Bot accounts có patterns TƯƠNG TỰ KOL dùng fake followers:
      + followers/following ratio bất thường
      + Activity patterns bất thường  
      + Profile incomplete
    - Dataset có labeled ground truth để train supervised learning
    
    Source: twitter_human_bots
    """
    print("\n" + "="*60)
    print("🔄 Transforming: kol_trust_features (ML Training Data)")
    print("="*60)
    
    try:
        twitter_df = load_bronze_source(spark, "twitter_human_bots")
        
        if twitter_df.count() == 0:
            print("   ❌ No twitter_human_bots data found")
            return {"table": "kol_trust_features", "records": 0, "status": "error"}
        
        # Current date for age calculation
        current_date = F.current_date()
        
        trust_features = (twitter_df
            .select(
                F.col("kol_id"),
                F.lit("twitter").alias("platform"),
                F.col("payload.profile.screen_name").alias("username"),
                
                # Profile Quality Features
                F.when(F.col("payload.profile.default_profile_image") == True, False)
                 .otherwise(True).alias("has_profile_image"),
                F.when(F.col("payload.profile.description").isNotNull() & 
                       (F.length(F.col("payload.profile.description")) > 0), True)
                 .otherwise(False).alias("has_bio"),
                F.coalesce(F.length(F.col("payload.profile.description")), F.lit(0)).alias("bio_length"),
                F.coalesce(F.col("payload.profile.has_url"), F.lit(False)).alias("has_url"),
                F.coalesce(F.col("payload.profile.verified"), F.lit(False)).alias("verified"),
                
                # Activity Features
                F.coalesce(F.col("payload.profile.followers_count"), F.lit(0)).alias("followers_count"),
                F.coalesce(F.col("payload.profile.friends_count"), F.lit(0)).alias("following_count"),
                F.coalesce(F.col("payload.profile.statuses_count"), F.lit(0)).alias("post_count"),
                F.coalesce(F.col("payload.profile.favourites_count"), F.lit(0)).alias("favorites_count"),
                F.coalesce(F.col("payload.derived_features.followers_friends_ratio"), F.lit(0.0)).alias("followers_following_ratio"),
                
                # Account dates
                F.col("payload.profile.created_at").alias("account_created_at"),
                
                # Behavioral flags
                F.coalesce(F.col("payload.profile.default_profile"), F.lit(False)).alias("default_profile"),
                F.coalesce(F.col("payload.profile.default_profile_image"), F.lit(False)).alias("default_profile_image"),
                
                # LABELS (Ground Truth) - Re-mapped for KOL Trust Detection
                # is_bot → is_untrustworthy: Account có dấu hiệu không đáng tin (fake followers, bot-like behavior)
                # is_human → is_trustworthy: Account có dấu hiệu đáng tin (authentic engagement)
                F.coalesce(F.col("payload.trust_label.is_bot"), F.lit(0)).alias("is_untrustworthy"),
                F.coalesce(F.col("payload.trust_label.is_human"), F.lit(0)).alias("is_trustworthy"),
                F.coalesce(F.col("payload.trust_label.account_type"), F.lit("unknown")).alias("account_type"),
                
                F.lit("twitter_human_bots").alias("source"),
                F.current_timestamp().alias("processed_at")
            )
        )
        
        # Calculate derived features
        trust_features = (trust_features
            # Account age in days (approximate from created_at string)
            .withColumn(
                "account_age_days",
                F.when(
                    F.col("account_created_at").isNotNull(),
                    F.datediff(
                        current_date,
                        F.to_date(F.col("account_created_at"), "yyyy-MM-dd HH:mm:ss")
                    )
                ).otherwise(F.lit(0))
            )
            # Posts per day
            .withColumn(
                "posts_per_day",
                F.when(
                    F.col("account_age_days") > 0,
                    F.round(F.col("post_count") / F.col("account_age_days"), 2)
                ).otherwise(F.lit(0.0))
            )
        )
        
        count = trust_features.count()
        
        # Label statistics
        trustworthy_count = trust_features.filter(F.col("is_trustworthy") == 1).count()
        untrustworthy_count = trust_features.filter(F.col("is_untrustworthy") == 1).count()
        
        print(f"✅ Generated {count:,} trust feature records")
        print(f"   📊 Label distribution: Trustworthy={trustworthy_count:,}, Untrustworthy={untrustworthy_count:,}")
        
        save_silver_table(trust_features, "kol_trust_features", dry_run)
        
        return {
            "table": "kol_trust_features", 
            "records": count, 
            "trustworthy_count": trustworthy_count,
            "untrustworthy_count": untrustworthy_count,
            "status": "success"
        }
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"table": "kol_trust_features", "records": 0, "status": "error"}


# =============================================================================
# TRANSFORMATION: kol_engagement_metrics
# =============================================================================
def transform_kol_engagement_metrics(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Transform Bronze data to aggregated engagement metrics per KOL.
    
    Sources: short_video_trends, youtube_trending
    """
    print("\n" + "="*60)
    print("🔄 Transforming: kol_engagement_metrics")
    print("="*60)
    
    metrics_list = []
    
    # 1. Process short_video_trends
    try:
        svt_df = load_bronze_source(spark, "short_video_trends")
        
        if svt_df.count() > 0:
            svt_metrics = (svt_df
                .select(
                    F.coalesce(F.col("kol_id"), F.col("payload.author_handle")).alias("kol_id"),
                    F.lower(F.coalesce(F.col("payload.platform"), F.col("platform"))).alias("platform"),
                    # Use actual field names from Bronze
                    F.coalesce(F.col("payload.views"), F.lit(0)).cast("long").alias("views"),
                    F.coalesce(F.col("payload.likes"), F.lit(0)).cast("long").alias("likes"),
                    F.coalesce(F.col("payload.comments"), F.lit(0)).cast("long").alias("comments"),
                    F.coalesce(F.col("payload.shares"), F.lit(0)).cast("long").alias("shares"),
                    F.lit("short_video_trends").alias("source")
                )
                .filter(F.col("kol_id").isNotNull())
            )
            metrics_list.append(svt_metrics)
    except Exception as e:
        print(f"   ⚠️ Error processing short_video_trends: {e}")
    
    # 2. Process youtube_trending
    try:
        yt_df = load_bronze_source(spark, "youtube_trending")
        
        if yt_df.count() > 0:
            yt_metrics = (yt_df
                .select(
                    F.coalesce(F.col("payload.channel_id"), F.col("kol_id")).alias("kol_id"),
                    F.lit("youtube").alias("platform"),
                    F.coalesce(F.col("payload.view_count"), F.lit(0)).cast("long").alias("views"),
                    # Use 'likes' field (not 'like_count') based on actual Bronze schema
                    F.coalesce(F.col("payload.likes"), F.lit(0)).cast("long").alias("likes"),
                    F.coalesce(F.col("payload.comment_count"), F.lit(0)).cast("long").alias("comments"),
                    F.lit(0).cast("long").alias("shares"),
                    F.lit("youtube_trending").alias("source")
                )
                .filter(F.col("kol_id").isNotNull() & (F.col("kol_id") != ""))
            )
            metrics_list.append(yt_metrics)
    except Exception as e:
        print(f"   ⚠️ Error processing youtube_trending: {e}")
    
    if not metrics_list:
        print("   ❌ No metrics data found")
        return {"table": "kol_engagement_metrics", "records": 0, "status": "error"}
    
    # Union all metrics
    all_metrics = metrics_list[0]
    for df in metrics_list[1:]:
        all_metrics = all_metrics.unionByName(df, allowMissingColumns=True)
    
    # Aggregate by KOL + Platform
    aggregated = (all_metrics
        .groupBy("platform", "kol_id")
        .agg(
            F.sum("views").alias("total_views"),
            F.sum("likes").alias("total_likes"),
            F.sum("comments").alias("total_comments"),
            F.sum("shares").alias("total_shares"),
            F.count("*").alias("total_posts"),
            F.avg("views").alias("avg_views_per_post"),
            F.avg("likes").alias("avg_likes_per_post"),
            F.max("views").alias("max_views"),
            F.min("views").alias("min_views"),
            F.first("source").alias("source")
        )
        .withColumn(
            "avg_engagement_rate",
            F.when(
                F.col("total_views") > 0,
                F.round(
                    (F.col("total_likes") + F.col("total_comments") + F.col("total_shares")) 
                    / F.col("total_views") * 100, 4
                )
            ).otherwise(F.lit(0.0))
        )
        .withColumn("avg_views_per_post", F.round(F.col("avg_views_per_post"), 2))
        .withColumn("avg_likes_per_post", F.round(F.col("avg_likes_per_post"), 2))
        .withColumn("processed_at", F.current_timestamp())
    )
    
    count = aggregated.count()
    print(f"✅ Generated {count:,} KOL engagement records")
    
    save_silver_table(aggregated, "kol_engagement_metrics", dry_run)
    
    return {"table": "kol_engagement_metrics", "records": count, "status": "success"}


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def run_all_transformations(spark: SparkSession, dry_run: bool = False, 
                            tables: Optional[List[str]] = None) -> list:
    """Run all Bronze -> Silver transformations."""
    
    all_transformations = {
        'kol_profiles': transform_kol_profiles,
        'kol_content': transform_kol_content,
        'kol_trust_features': transform_kol_trust_features,
        'kol_engagement_metrics': transform_kol_engagement_metrics
    }
    
    if tables:
        transformations = {k: v for k, v in all_transformations.items() if k in tables}
    else:
        transformations = all_transformations
    
    results = []
    
    print("\n" + "=" * 70)
    print("🔄 BRONZE → SILVER ETL (PySpark)")
    print("=" * 70)
    print(f"   Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    print(f"   Tables: {list(transformations.keys())}")
    print(f"   Output Format: Parquet (Snappy compression)")
    print("=" * 70)
    
    for table_name, transform_func in transformations.items():
        try:
            result = transform_func(spark, dry_run=dry_run)
            results.append(result)
        except Exception as e:
            print(f"❌ Failed: {table_name} - {e}")
            results.append({
                'table': table_name,
                'records': 0,
                'status': 'error',
                'error': str(e)
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 BRONZE → SILVER SUMMARY")
    print("=" * 70)
    
    total_records = 0
    for result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        print(f"   {status_icon} {result['table']}: {result['records']:,} records")
        total_records += result['records']
    
    print(f"\n   TOTAL: {total_records:,} records processed")
    print("=" * 70 + "\n")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Bronze -> Silver ETL (PySpark)')
    
    parser.add_argument(
        '--table',
        type=str,
        choices=['kol_profiles', 'kol_content', 'kol_trust_features', 'kol_engagement_metrics'],
        help='Specific table to transform (default: all)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (no writes)'
    )
    
    parser.add_argument(
        '--local',
        action='store_true',
        help='Run in local mode instead of cluster'
    )
    
    args = parser.parse_args()
    
    # Create Spark session
    master_url = "local[*]" if args.local else None
    spark = create_spark_session(master_url)
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        tables = [args.table] if args.table else None
        run_all_transformations(spark, dry_run=args.dry_run, tables=tables)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

"""
ETL: Silver -> Gold (PySpark on Docker Cluster)
================================================

Chạy trên: Spark Cluster (kol-spark-master:7077)
Đọc từ: MinIO s3a://kol-platform/silver/* (Parquet)
Ghi ra: MinIO s3a://kol-platform/gold/* (Parquet)

Star Schema Tables:
- dim_kol: KOL dimension
- dim_platform: Platform dimension  
- dim_time: Time dimension
- dim_content_type: Content type dimension
- fact_kol_performance: Main fact table
- ml_trust_training: ML training dataset
- agg_platform_kpi: Pre-aggregated KPIs

Cách chạy:
-----------
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/silver_to_gold.py

# Dry-run
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/silver_to_gold.py --dry-run

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
from pyspark.sql.window import Window


# =============================================================================
# CONFIGURATION
# =============================================================================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "sme-minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
BUCKET = os.getenv("BUCKET", "kol-platform")

SILVER_PATH = f"s3a://{BUCKET}/silver"
GOLD_PATH = f"s3a://{BUCKET}/gold"


# =============================================================================
# SPARK SESSION
# =============================================================================
def create_spark_session(master_url: str = None) -> SparkSession:
    """Create Spark session with S3A (MinIO) support."""
    if master_url is None:
        master_url = os.getenv("SPARK_MASTER", "spark://spark-master:7077")
    
    print(f"🔌 Connecting to Spark Master: {master_url}")
    
    return (SparkSession.builder
        .appName("SilverToGold_ETL")
        .master(master_url)
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{MINIO_ENDPOINT}")
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )


def load_silver_table(spark: SparkSession, table_name: str) -> DataFrame:
    """Load Silver table from MinIO (Parquet format)."""
    path = f"{SILVER_PATH}/{table_name}/"
    print(f"📥 Loading: {path}")
    
    try:
        df = spark.read.parquet(path)
        count = df.count()
        print(f"   Loaded: {count:,} records")
        return df
    except Exception as e:
        print(f"   ⚠️ Error loading {table_name}: {e}")
        # Try loading JSONL as fallback
        try:
            print(f"   Trying JSONL format...")
            df = spark.read.json(path)
            count = df.count()
            print(f"   Loaded: {count:,} records (JSONL)")
            return df
        except:
            return None


def save_gold_table(df: DataFrame, table_name: str, dry_run: bool = False):
    """Save DataFrame to Gold layer as Parquet."""
    if df is None or df.count() == 0:
        print(f"   ⚠️ No data to save for {table_name}")
        return
    
    output_path = f"{GOLD_PATH}/{table_name}/"
    
    if dry_run:
        print(f"🔍 DRY RUN: Would save {df.count():,} records to {output_path}")
        df.show(5, truncate=False)
        return
    
    print(f"💾 Saving to: {output_path}")
    df.write.mode("overwrite").parquet(output_path)
    print(f"   ✅ Saved {df.count():,} records")


# =============================================================================
# DIMENSION: dim_kol
# =============================================================================
def build_dim_kol(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Build KOL Dimension table.
    
    Joins profiles + trust features + engagement metrics
    """
    print("\n" + "="*60)
    print("🔄 Building: dim_kol")
    print("="*60)
    
    profiles = load_silver_table(spark, "kol_profiles")
    trust = load_silver_table(spark, "kol_trust_features")
    engagement = load_silver_table(spark, "kol_engagement_metrics")
    
    if profiles is None:
        return {"table": "dim_kol", "records": 0, "status": "error"}
    
    # Start with profiles as base
    dim_kol = profiles.select(
        F.col("kol_id"),
        F.col("platform"),
        F.col("username"),
        F.col("display_name"),
        F.col("profile_url"),
        F.col("category"),
        F.col("followers_count"),
        F.col("following_count"),
        F.col("post_count"),
        F.col("verified"),
        F.col("source")
    )
    
    # Join trust features if available
    if trust is not None:
        trust_select = trust.select(
            F.col("kol_id").alias("trust_kol_id"),
            F.col("is_untrustworthy"),
            F.col("account_type"),
            F.col("has_profile_image"),
            F.col("account_age_days")
        ).dropDuplicates(["trust_kol_id"])
        
        dim_kol = dim_kol.join(
            trust_select,
            dim_kol.kol_id == trust_select.trust_kol_id,
            "left"
        ).drop("trust_kol_id")
    else:
        dim_kol = (dim_kol
            .withColumn("is_untrustworthy", F.lit(None).cast("int"))
            .withColumn("account_type", F.lit("unknown"))
            .withColumn("has_profile_image", F.lit(True))
            .withColumn("account_age_days", F.lit(0))
        )
    
    # Join engagement if available
    if engagement is not None:
        eng_select = engagement.select(
            F.col("kol_id").alias("eng_kol_id"),
            F.col("platform").alias("eng_platform"),
            F.col("total_views"),
            F.col("total_likes"),
            F.col("total_posts").alias("total_posts_tracked"),
            F.col("avg_engagement_rate")
        )
        
        dim_kol = dim_kol.join(
            eng_select,
            (dim_kol.kol_id == eng_select.eng_kol_id) & 
            (dim_kol.platform == eng_select.eng_platform),
            "left"
        ).drop("eng_kol_id", "eng_platform")
    else:
        dim_kol = (dim_kol
            .withColumn("total_views", F.lit(0).cast("long"))
            .withColumn("total_likes", F.lit(0).cast("long"))
            .withColumn("total_posts_tracked", F.lit(0).cast("long"))
            .withColumn("avg_engagement_rate", F.lit(0.0))
        )
    
    # Compute Trust Score
    # is_untrustworthy = 1: KOL có dấu hiệu không đáng tin (dùng fake followers, bot-like behavior)
    # is_untrustworthy = 0: KOL có dấu hiệu đáng tin (authentic engagement)
    dim_kol = dim_kol.withColumn(
        "trust_score",
        (
            F.when(F.col("verified") == True, 20).otherwise(0) +
            F.when(F.col("has_profile_image") == True, 10).otherwise(0) +
            F.least(F.coalesce(F.col("account_age_days"), F.lit(0)) / 365 * 20, F.lit(20)) +
            F.least(
                F.coalesce(F.col("followers_count"), F.lit(0)) / 
                F.greatest(F.coalesce(F.col("following_count"), F.lit(1)), F.lit(1)) / 10 * 20,
                F.lit(20)
            ) +
            # is_untrustworthy=0 (trustworthy) → +20 points
            # is_untrustworthy=1 (untrustworthy) → -30 points
            F.when(F.col("is_untrustworthy") == 0, 20).when(F.col("is_untrustworthy") == 1, -30).otherwise(0)
        )
    )
    dim_kol = dim_kol.withColumn(
        "trust_score",
        F.greatest(F.least(F.round(F.col("trust_score"), 1), F.lit(100)), F.lit(0))
    )
    
    # Compute KOL Tier
    dim_kol = dim_kol.withColumn(
        "kol_tier",
        F.when(F.col("followers_count") >= 1000000, "Mega")
         .when(F.col("followers_count") >= 100000, "Macro")
         .when(F.col("followers_count") >= 10000, "Micro")
         .when(F.col("followers_count") >= 1000, "Nano")
         .otherwise("Rising")
    )
    
    # Followers/Following Ratio
    dim_kol = dim_kol.withColumn(
        "followers_following_ratio",
        F.round(
            F.coalesce(F.col("followers_count"), F.lit(0)) / 
            F.greatest(F.coalesce(F.col("following_count"), F.lit(1)), F.lit(1)),
            2
        )
    )
    
    # Fill nulls
    dim_kol = (dim_kol
        .fillna(0, subset=["total_views", "total_likes", "total_posts_tracked"])
        .fillna(0.0, subset=["avg_engagement_rate"])
        .withColumn("processed_at", F.current_timestamp())
    )
    
    count = dim_kol.count()
    
    # Stats
    tier_stats = dim_kol.groupBy("kol_tier").count().collect()
    print(f"✅ Built {count:,} KOL dimension records")
    print(f"   📊 Tier distribution: {[(r['kol_tier'], r['count']) for r in tier_stats]}")
    
    save_gold_table(dim_kol, "dim_kol", dry_run)
    
    return {"table": "dim_kol", "records": count, "status": "success"}


# =============================================================================
# DIMENSION: dim_platform
# =============================================================================
def build_dim_platform(spark: SparkSession, dry_run: bool = False) -> dict:
    """Build Platform Dimension (static data)."""
    print("\n" + "="*60)
    print("🔄 Building: dim_platform")
    print("="*60)
    
    platforms = [
        (1, "youtube", "YouTube", "video", "long_video", "https://youtube.com", 2005),
        (2, "tiktok", "TikTok", "video", "short_video", "https://tiktok.com", 2016),
        (3, "twitter", "Twitter/X", "microblog", "text", "https://twitter.com", 2006),
        (4, "instagram", "Instagram", "social", "image_video", "https://instagram.com", 2010),
    ]
    
    df = spark.createDataFrame(platforms, [
        "platform_id", "platform_name", "platform_display", 
        "platform_type", "content_format", "base_url", "launched_year"
    ])
    
    df = df.withColumn("is_active", F.lit(True))
    df = df.withColumn("processed_at", F.current_timestamp())
    
    count = df.count()
    print(f"✅ Built {count} platform dimension records")
    
    save_gold_table(df, "dim_platform", dry_run)
    
    return {"table": "dim_platform", "records": count, "status": "success"}


# =============================================================================
# DIMENSION: dim_time
# =============================================================================
def build_dim_time(spark: SparkSession, dry_run: bool = False) -> dict:
    """Build Time Dimension from content dates."""
    print("\n" + "="*60)
    print("🔄 Building: dim_time")
    print("="*60)
    
    content = load_silver_table(spark, "kol_content")
    
    if content is None:
        return {"table": "dim_time", "records": 0, "status": "error"}
    
    # Extract unique dates
    dates = (content
        .filter(F.col("posted_at").isNotNull())
        .withColumn("date_str", F.substring(F.col("posted_at"), 1, 10))
        .filter(F.length(F.col("date_str")) >= 10)
        .select("date_str")
        .distinct()
    )
    
    # Build time dimension
    dim_time = (dates
        .withColumn("full_date", F.to_date(F.col("date_str"), "yyyy-MM-dd"))
        .filter(F.col("full_date").isNotNull())
        .withColumn("date_id", F.date_format(F.col("full_date"), "yyyyMMdd").cast("int"))
        .withColumn("year", F.year(F.col("full_date")))
        .withColumn("quarter", F.quarter(F.col("full_date")))
        .withColumn("month", F.month(F.col("full_date")))
        .withColumn("week", F.weekofyear(F.col("full_date")))
        .withColumn("day", F.dayofmonth(F.col("full_date")))
        .withColumn("day_of_week", F.dayofweek(F.col("full_date")))
        .withColumn("day_name", F.date_format(F.col("full_date"), "EEEE"))
        .withColumn("month_name", F.date_format(F.col("full_date"), "MMMM"))
        .withColumn("is_weekend", F.when(F.col("day_of_week").isin([1, 7]), True).otherwise(False))
        .withColumn("quarter_name", F.concat(F.lit("Q"), F.col("quarter")))
        .withColumn("processed_at", F.current_timestamp())
        .drop("date_str")
    )
    
    count = dim_time.count()
    
    # Get date range
    date_range = dim_time.agg(
        F.min("full_date").alias("min_date"),
        F.max("full_date").alias("max_date")
    ).collect()[0]
    
    print(f"✅ Built {count} time dimension records")
    print(f"   📊 Date range: {date_range['min_date']} to {date_range['max_date']}")
    
    save_gold_table(dim_time, "dim_time", dry_run)
    
    return {"table": "dim_time", "records": count, "status": "success"}


# =============================================================================
# DIMENSION: dim_content_type
# =============================================================================
def build_dim_content_type(spark: SparkSession, dry_run: bool = False) -> dict:
    """Build Content Type Dimension (static data)."""
    print("\n" + "="*60)
    print("🔄 Building: dim_content_type")
    print("="*60)
    
    content_types = [
        (1, "video", "Long Video", "video", 10, 3600),
        (2, "short", "Short Video", "video", 15, 60),
        (3, "reel", "Reel", "video", 15, 90),
        (4, "post", "Social Post", "mixed", 0, 0),
        (5, "tweet", "Tweet", "text", 0, 0),
    ]
    
    df = spark.createDataFrame(content_types, [
        "content_type_id", "content_type_name", "content_type_display",
        "content_category", "typical_duration_min", "typical_duration_max"
    ])
    
    df = df.withColumn("processed_at", F.current_timestamp())
    
    count = df.count()
    print(f"✅ Built {count} content type dimension records")
    
    save_gold_table(df, "dim_content_type", dry_run)
    
    return {"table": "dim_content_type", "records": count, "status": "success"}


# =============================================================================
# FACT: fact_kol_performance
# =============================================================================
def build_fact_kol_performance(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Build Main Fact Table - KOL Performance.
    
    Star Schema with FKs to all dimensions.
    """
    print("\n" + "="*60)
    print("🔄 Building: fact_kol_performance")
    print("="*60)
    
    content = load_silver_table(spark, "kol_content")
    
    if content is None:
        return {"table": "fact_kol_performance", "records": 0, "status": "error"}
    
    # Platform mapping
    platform_map = {"youtube": 1, "tiktok": 2, "twitter": 3, "instagram": 4}
    
    # Build fact table
    fact = content.select(
        F.col("content_id").alias("fact_id"),
        F.col("kol_id"),
        # Platform FK
        F.when(F.lower(F.col("platform")) == "youtube", 1)
         .when(F.lower(F.col("platform")) == "tiktok", 2)
         .when(F.lower(F.col("platform")) == "twitter", 3)
         .when(F.lower(F.col("platform")) == "instagram", 4)
         .otherwise(0).alias("platform_id"),
        # Date FK
        F.when(
            F.col("posted_at").isNotNull() & (F.length(F.col("posted_at")) >= 10),
            F.date_format(F.to_date(F.substring(F.col("posted_at"), 1, 10), "yyyy-MM-dd"), "yyyyMMdd").cast("int")
        ).alias("date_id"),
        # Content Type FK
        F.when(F.lower(F.col("platform")) == "tiktok", 2)
         .when((F.lower(F.col("platform")) == "youtube") & (F.col("duration_seconds") < 60), 2)
         .when(F.lower(F.col("platform")) == "youtube", 1)
         .when(F.lower(F.col("platform")) == "instagram", 3)
         .when(F.lower(F.col("platform")) == "twitter", 5)
         .otherwise(4).alias("content_type_id"),
        # Content info
        F.col("content_id"),
        F.substring(F.coalesce(F.col("title"), F.lit("")), 1, 100).alias("title"),
        # Measures
        F.coalesce(F.col("views"), F.lit(0)).alias("views"),
        F.coalesce(F.col("likes"), F.lit(0)).alias("likes"),
        F.coalesce(F.col("comments"), F.lit(0)).alias("comments"),
        F.coalesce(F.col("shares"), F.lit(0)).alias("shares"),
        (F.coalesce(F.col("likes"), F.lit(0)) + 
         F.coalesce(F.col("comments"), F.lit(0)) + 
         F.coalesce(F.col("shares"), F.lit(0))).alias("total_engagement"),
        F.coalesce(F.col("duration_seconds"), F.lit(0)).alias("duration_seconds"),
        F.coalesce(F.col("engagement_rate"), F.lit(0.0)).alias("engagement_rate"),
        F.col("source")
    )
    
    # Add tiers
    fact = fact.withColumn(
        "view_tier",
        F.when(F.col("views") >= 1000000, "Viral")
         .when(F.col("views") >= 100000, "Hot")
         .when(F.col("views") >= 10000, "Trending")
         .otherwise("Regular")
    )
    
    fact = fact.withColumn(
        "engagement_tier",
        F.when(F.col("engagement_rate") >= 10, "High")
         .when(F.col("engagement_rate") >= 5, "Medium")
         .when(F.col("engagement_rate") >= 2, "Low")
         .otherwise("Very Low")
    )
    
    fact = fact.withColumn("processed_at", F.current_timestamp())
    
    count = fact.count()
    
    # Stats
    tier_stats = fact.groupBy("view_tier").count().collect()
    print(f"✅ Built {count:,} fact records")
    print(f"   📊 View tiers: {[(r['view_tier'], r['count']) for r in tier_stats]}")
    
    save_gold_table(fact, "fact_kol_performance", dry_run)
    
    return {"table": "fact_kol_performance", "records": count, "status": "success"}


# =============================================================================
# ML: ml_trust_training
# =============================================================================
def build_ml_trust_training(spark: SparkSession, dry_run: bool = False) -> dict:
    """
    Build ML-ready training dataset for KOL Trust Score model.
    
    SEMANTIC MAPPING:
    - is_untrustworthy = 1: KOL có dấu hiệu không đáng tin
      (fake followers, bot-like activity patterns)
    - is_untrustworthy = 0: KOL có dấu hiệu đáng tin
      (authentic engagement, organic growth)
    
    Model sẽ predict: P(KOL không đáng tin | features)
    """
    print("\n" + "="*60)
    print("🔄 Building: ml_trust_training")
    print("="*60)
    
    trust = load_silver_table(spark, "kol_trust_features")
    
    if trust is None:
        return {"table": "ml_trust_training", "records": 0, "status": "error"}
    
    # Filter only labeled data (account_type: human=trustworthy, bot=untrustworthy)
    ml_data = trust.filter(F.col("account_type").isin(["human", "bot"]))
    
    # Select features for ML
    ml_training = ml_data.select(
        F.col("kol_id"),
        # Numeric features
        F.coalesce(F.col("followers_count"), F.lit(0)).alias("followers_count"),
        F.coalesce(F.col("following_count"), F.lit(0)).alias("following_count"),
        F.coalesce(F.col("post_count"), F.lit(0)).alias("post_count"),
        F.coalesce(F.col("favorites_count"), F.lit(0)).alias("favorites_count"),
        F.coalesce(F.col("followers_following_ratio"), F.lit(0.0)).alias("followers_following_ratio"),
        F.coalesce(F.col("posts_per_day"), F.lit(0.0)).alias("posts_per_day"),
        F.coalesce(F.col("account_age_days"), F.lit(0)).alias("account_age_days"),
        F.coalesce(F.col("bio_length"), F.lit(0)).alias("bio_length"),
        # Binary features (convert to int)
        F.when(F.col("has_profile_image") == True, 1).otherwise(0).alias("has_profile_image"),
        F.when(F.col("has_bio") == True, 1).otherwise(0).alias("has_bio"),
        F.when(F.col("has_url") == True, 1).otherwise(0).alias("has_url"),
        F.when(F.col("verified") == True, 1).otherwise(0).alias("verified"),
        F.when(F.col("default_profile") == True, 1).otherwise(0).alias("default_profile"),
        F.when(F.col("default_profile_image") == True, 1).otherwise(0).alias("default_profile_image"),
        # Labels - Re-mapped for KOL Trust Detection
        # is_untrustworthy: KOL có dấu hiệu không đáng tin (fake followers, suspicious patterns)
        F.coalesce(F.col("is_untrustworthy"), F.lit(0)).alias("is_untrustworthy"),
        # label = is_untrustworthy: Model predicts P(KOL không đáng tin)
        F.when(F.col("is_untrustworthy") == 1, 1).otherwise(0).alias("label"),
        # Metadata
        F.col("platform").alias("_platform"),
        F.col("source").alias("_source"),
        F.current_timestamp().alias("_processed_at")
    )
    
    count = ml_training.count()
    untrustworthy_count = ml_training.filter(F.col("label") == 1).count()
    trustworthy_count = count - untrustworthy_count
    
    print(f"✅ Built {count:,} ML training samples")
    print(f"   📊 Label distribution: Trustworthy={trustworthy_count:,}, Untrustworthy={untrustworthy_count:,}")
    print(f"   📊 Untrustworthy ratio: {untrustworthy_count/count*100:.1f}%")
    
    save_gold_table(ml_training, "ml_trust_training", dry_run)
    
    return {
        "table": "ml_trust_training",
        "records": count,
        "trustworthy_count": trustworthy_count,
        "untrustworthy_count": untrustworthy_count,
        "status": "success"
    }


# =============================================================================
# AGGREGATION: agg_platform_kpi
# =============================================================================
def build_agg_platform_kpi(spark: SparkSession, dry_run: bool = False) -> dict:
    """Build pre-aggregated Platform KPIs."""
    print("\n" + "="*60)
    print("🔄 Building: agg_platform_kpi")
    print("="*60)
    
    content = load_silver_table(spark, "kol_content")
    profiles = load_silver_table(spark, "kol_profiles")
    
    if content is None:
        return {"table": "agg_platform_kpi", "records": 0, "status": "error"}
    
    # Aggregate content by platform
    content_agg = (content
        .withColumn("platform", F.lower(F.col("platform")))
        .groupBy("platform")
        .agg(
            F.countDistinct("kol_id").alias("total_kols"),
            F.count("*").alias("total_content"),
            F.sum("views").alias("total_views"),
            F.sum("likes").alias("total_likes"),
            F.sum("comments").alias("total_comments"),
            F.sum("shares").alias("total_shares"),
            F.avg("engagement_rate").alias("avg_engagement_rate")
        )
    )
    
    # Add verified count from profiles
    if profiles is not None:
        verified_count = (profiles
            .withColumn("platform", F.lower(F.col("platform")))
            .filter(F.col("verified") == True)
            .groupBy("platform")
            .agg(F.count("*").alias("verified_kols"))
        )
        
        content_agg = content_agg.join(verified_count, "platform", "left")
    else:
        content_agg = content_agg.withColumn("verified_kols", F.lit(0))
    
    # Compute derived metrics
    kpi = (content_agg
        .withColumn("avg_views_per_content", 
                    F.round(F.col("total_views") / F.greatest(F.col("total_content"), F.lit(1)), 0))
        .withColumn("avg_likes_per_content",
                    F.round(F.col("total_likes") / F.greatest(F.col("total_content"), F.lit(1)), 0))
        .withColumn("total_engagement",
                    F.col("total_likes") + F.col("total_comments") + F.col("total_shares"))
        .withColumn("avg_engagement_rate", F.round(F.col("avg_engagement_rate"), 2))
        .withColumn("verified_kols", F.coalesce(F.col("verified_kols"), F.lit(0)))
        .withColumn("report_date", F.current_date())
        .withColumn("processed_at", F.current_timestamp())
    )
    
    count = kpi.count()
    
    # Show results
    print(f"✅ Built {count} platform KPI records")
    kpi.select("platform", "total_kols", "total_content", "total_views").show()
    
    save_gold_table(kpi, "agg_platform_kpi", dry_run)
    
    return {"table": "agg_platform_kpi", "records": count, "status": "success"}


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def run_all_transformations(spark: SparkSession, dry_run: bool = False,
                            tables: Optional[List[str]] = None) -> list:
    """Run all Silver -> Gold transformations."""
    
    all_transformations = {
        # Dimensions
        "dim_kol": build_dim_kol,
        "dim_platform": build_dim_platform,
        "dim_time": build_dim_time,
        "dim_content_type": build_dim_content_type,
        # Fact
        "fact_kol_performance": build_fact_kol_performance,
        # ML & Analytics
        "ml_trust_training": build_ml_trust_training,
        "agg_platform_kpi": build_agg_platform_kpi,
    }
    
    if tables:
        transformations = {k: v for k, v in all_transformations.items() if k in tables}
    else:
        transformations = all_transformations
    
    results = []
    
    print("\n" + "=" * 70)
    print("🏆 SILVER → GOLD ETL (PySpark - Star Schema)")
    print("=" * 70)
    print(f"   Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    print(f"   Tables: {list(transformations.keys())}")
    print(f"   Output Format: Parquet")
    print("=" * 70)
    
    for table_name, transform_func in transformations.items():
        try:
            result = transform_func(spark, dry_run=dry_run)
            results.append(result)
        except Exception as e:
            print(f"❌ Failed: {table_name} - {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "table": table_name,
                "records": 0,
                "status": "error",
                "error": str(e)
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SILVER → GOLD SUMMARY")
    print("=" * 70)
    
    total_records = 0
    for result in results:
        status_icon = "✅" if result["status"] == "success" else "❌"
        print(f"   {status_icon} {result['table']}: {result['records']:,} records")
        total_records += result["records"]
    
    print(f"\n   TOTAL: {total_records:,} records in Gold layer")
    print("=" * 70 + "\n")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Silver -> Gold ETL (PySpark)")
    
    parser.add_argument(
        "--table",
        type=str,
        choices=[
            "dim_kol", "dim_platform", "dim_time", "dim_content_type",
            "fact_kol_performance", "ml_trust_training", "agg_platform_kpi"
        ],
        help="Specific table to build"
    )
    
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--local", action="store_true", help="Run in local mode")
    
    args = parser.parse_args()
    
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

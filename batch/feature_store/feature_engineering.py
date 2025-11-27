"""
KOL TRUST SCORE FEATURE ENGINEERING (PySpark on Docker Cluster)
================================================================

Chạy trên: Spark Cluster (kol-spark-master:7077)
Đọc từ: MinIO s3a://kol-platform/gold/ml_trust_training/
Ghi ra: MinIO s3a://kol-platform/gold/ml_trust_features_engineered/

BÀI TOÁN: Detect KOL không đáng tin (dùng fake followers, bot-like behavior)
- label = 1: KOL không đáng tin (is_untrustworthy)
- label = 0: KOL đáng tin (is_trustworthy)

Feature Engineering Pipeline:
1. Log Transformations (giảm skewness cho count features)
2. Ratio Capping (clip outliers)  
3. Derived Features (engagement rate, activity score, etc.)
4. Untrustworthy Indicator Features (patterns của KOL dùng fake followers)
5. Binning (discretize continuous features)
6. Feature Interactions

Cách chạy:
-----------
# Submit từ host vào Spark cluster (trong Docker)
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/feature_store/feature_engineering.py

# Dry-run mode (chỉ show stats, không save)
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/feature_store/feature_engineering.py --dry-run

# Với sample 10%
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/feature_store/feature_engineering.py --sample 0.1
"""

import os
import sys
import argparse
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, FloatType, DoubleType
)
from pyspark.ml.feature import VectorAssembler, StandardScaler


# =============================================================================
# CONFIGURATION (Docker Network - sme-minio là MinIO service)
# =============================================================================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "sme-minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
BUCKET = os.getenv("BUCKET", "kol-platform")

INPUT_PATH = f"s3a://{BUCKET}/gold/ml_trust_training/"
OUTPUT_PATH = f"s3a://{BUCKET}/gold/ml_trust_features_engineered/"


# =============================================================================
# SCHEMA DEFINITION
# =============================================================================
ML_TRUST_SCHEMA = StructType([
    StructField("kol_id", StringType(), True),
    StructField("followers_count", IntegerType(), True),
    StructField("following_count", IntegerType(), True),
    StructField("post_count", IntegerType(), True),
    StructField("favorites_count", IntegerType(), True),
    StructField("followers_following_ratio", FloatType(), True),
    StructField("posts_per_day", FloatType(), True),
    StructField("account_age_days", IntegerType(), True),
    StructField("bio_length", IntegerType(), True),
    StructField("has_profile_image", IntegerType(), True),
    StructField("has_bio", IntegerType(), True),
    StructField("has_url", IntegerType(), True),
    StructField("verified", IntegerType(), True),
    StructField("default_profile", IntegerType(), True),
    StructField("default_profile_image", IntegerType(), True),
    # is_untrustworthy: KOL có dấu hiệu không đáng tin (fake followers, suspicious patterns)
    StructField("is_untrustworthy", IntegerType(), True),
    # label = is_untrustworthy: Model predicts P(KOL không đáng tin)
    StructField("label", IntegerType(), True),
    StructField("_platform", StringType(), True),
    StructField("_source", StringType(), True),
    StructField("_processed_at", StringType(), True),
])


def create_spark_session(master_url: str = None):
    """
    Create Spark session connected to cluster with S3A (MinIO) support.
    
    Args:
        master_url: Spark master URL. 
                    Default: spark://spark-master:7077 (Docker)
                    Use "local[*]" for local testing
    """
    if master_url is None:
        master_url = os.getenv("SPARK_MASTER", "spark://spark-master:7077")
    
    print(f"🔌 Connecting to Spark Master: {master_url}")
    print(f"📦 MinIO Endpoint: {MINIO_ENDPOINT}")
    
    builder = (SparkSession.builder
        .appName("TrustScore_FeatureEngineering")
        .master(master_url)
        
        # S3A configuration for MinIO
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{MINIO_ENDPOINT}")
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", 
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        
        # Spark performance configs
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.executor.memory", "1g")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.adaptive.enabled", "true")
        
        # Output format
        .config("spark.sql.parquet.compression.codec", "snappy")
    )
    
    return builder.getOrCreate()


def load_data(spark):
    """Load ml_trust_training data from MinIO via S3A (Parquet format)."""
    print(f"\n📥 Loading data from: {INPUT_PATH}")
    
    # Read as Parquet (Silver/Gold tables are Parquet)
    df = spark.read.parquet(INPUT_PATH)
    
    count = df.count()
    print(f"   Loaded: {count:,} records")
    
    # Show schema
    print(f"   Schema: {df.columns}")
    
    return df


def feature_engineering(df):
    """
    Comprehensive Feature Engineering Pipeline.
    
    Transforms raw features into ML-ready features:
    - Log transforms for skewed distributions
    - Capped ratios to handle outliers
    - Derived features based on domain knowledge
    - Bot indicator flags
    - Feature binning for tree models
    - Feature interactions
    
    Returns DataFrame with engineered features.
    """
    print("\n" + "="*70)
    print("🔧 FEATURE ENGINEERING PIPELINE")
    print("="*70)
    
    # =========================================================================
    # 1. LOG TRANSFORMATIONS (giảm skewness)
    # =========================================================================
    print("\n📊 Step 1: Log Transformations...")
    df = (df
        .withColumn("log_followers", F.log1p(F.col("followers_count")))
        .withColumn("log_following", F.log1p(F.col("following_count")))
        .withColumn("log_posts", F.log1p(F.col("post_count")))
        .withColumn("log_favorites", F.log1p(F.col("favorites_count")))
        .withColumn("log_account_age", F.log1p(F.col("account_age_days")))
    )
    
    # =========================================================================
    # 2. RATIO CAPPING (clip outliers)
    # =========================================================================
    print("📊 Step 2: Ratio Capping (clip outliers)...")
    df = (df
        # Cap followers_following_ratio at 99th percentile (~10000)
        .withColumn(
            "followers_following_ratio_capped",
            F.when(F.col("followers_following_ratio") > 10000, 10000)
             .otherwise(F.col("followers_following_ratio"))
        )
        # Cap posts_per_day at reasonable limit
        .withColumn(
            "posts_per_day_capped",
            F.when(F.col("posts_per_day") > 50, 50)
             .otherwise(F.col("posts_per_day"))
        )
    )
    
    # =========================================================================
    # 3. DERIVED FEATURES (business logic)
    # =========================================================================
    print("📊 Step 3: Derived Features...")
    df = (df
        # Engagement Rate = favorites / (posts + 1)
        .withColumn(
            "engagement_rate",
            F.col("favorites_count") / (F.col("post_count") + 1)
        )
        # Activity Score = posts_per_day * sqrt(engagement_rate + 1)
        .withColumn(
            "activity_score",
            F.col("posts_per_day_capped") * F.sqrt(F.col("engagement_rate") + 1)
        )
        # Profile Completeness Score (0-1)
        .withColumn(
            "profile_completeness",
            (F.col("has_bio") + F.col("has_url") + F.col("has_profile_image")) / 3.0
        )
        # Followers per Day (growth rate proxy)
        .withColumn(
            "followers_per_day",
            F.col("followers_count") / (F.col("account_age_days") + 1)
        )
        # Posts per Follower (spamminess indicator)
        .withColumn(
            "posts_per_follower",
            F.col("post_count") / (F.col("followers_count") + 1)
        )
        # Following per Day (aggressiveness)
        .withColumn(
            "following_per_day",
            F.col("following_count") / (F.col("account_age_days") + 1)
        )
        # Bio length normalized (0-1, assuming max ~200 chars)
        .withColumn(
            "bio_length_norm",
            F.least(F.col("bio_length") / 200.0, F.lit(1.0))
        )
    )
    
    # =========================================================================
    # 4. UNTRUSTWORTHY INDICATOR FEATURES (KOL dùng fake followers patterns)
    # =========================================================================
    print("📊 Step 4: Untrustworthy Indicator Features...")
    df = (df
        # High activity flag - đăng quá nhiều, có thể dùng bot để post
        .withColumn(
            "high_activity_flag",
            F.when(F.col("posts_per_day") > 20, 1).otherwise(0)
        )
        # Low engagement with high posts - nhiều posts nhưng ít engagement = fake followers
        .withColumn(
            "low_engagement_high_posts",
            F.when(
                (F.col("engagement_rate") < 0.01) & (F.col("post_count") > 1000), 1
            ).otherwise(0)
        )
        # Default profile score - KOL thật thường customize profile
        .withColumn(
            "default_profile_score",
            F.col("default_profile") + F.col("default_profile_image")
        )
        # Suspicious growth - tăng followers bất thường nhanh = mua followers
        .withColumn(
            "suspicious_growth",
            F.when(
                (F.col("followers_per_day") > 100) & (F.col("account_age_days") < 365), 1
            ).otherwise(0)
        )
        # Fake follower indicator - followers nhiều nhưng engagement thấp
        .withColumn(
            "fake_follower_indicator",
            F.when(
                (F.col("followers_count") > 10000) & 
                (F.col("engagement_rate") < 0.1), 1
            ).otherwise(0)
        )
    )
    
    # =========================================================================
    # 5. BINNING (discretization for tree models)
    # =========================================================================
    print("📊 Step 5: Feature Binning...")
    df = (df
        # Followers tier: nano < micro < mid < macro < mega
        .withColumn(
            "followers_tier",
            F.when(F.col("followers_count") < 1000, 0)           # nano
             .when(F.col("followers_count") < 10000, 1)          # micro
             .when(F.col("followers_count") < 100000, 2)         # mid
             .when(F.col("followers_count") < 1000000, 3)        # macro
             .otherwise(4)                                        # mega
        )
        # Account age tier
        .withColumn(
            "account_age_tier",
            F.when(F.col("account_age_days") < 365, 0)           # < 1 year
             .when(F.col("account_age_days") < 730, 1)           # 1-2 years
             .when(F.col("account_age_days") < 1825, 2)          # 2-5 years
             .otherwise(3)                                        # 5+ years
        )
        # Activity tier
        .withColumn(
            "activity_tier",
            F.when(F.col("posts_per_day") < 0.5, 0)              # inactive
             .when(F.col("posts_per_day") < 2, 1)                # low
             .when(F.col("posts_per_day") < 10, 2)               # moderate
             .otherwise(3)                                        # high
        )
    )
    
    # =========================================================================
    # 6. FEATURE INTERACTIONS
    # =========================================================================
    print("📊 Step 6: Feature Interactions...")
    df = (df
        # Verified x Followers (verified accounts with many followers = trusted)
        .withColumn(
            "verified_followers_interaction",
            F.col("verified") * F.col("log_followers")
        )
        # Profile x Engagement (complete profile + high engagement = trusted)
        .withColumn(
            "profile_engagement_interaction",
            F.col("profile_completeness") * F.col("engagement_rate")
        )
        # Age x Activity (old account + moderate activity = trusted)
        .withColumn(
            "age_activity_interaction",
            F.col("log_account_age") * (1 / (F.col("posts_per_day_capped") + 1))
        )
    )
    
    # =========================================================================
    # 7. FILL NULLS
    # =========================================================================
    print("📊 Step 7: Fill null values...")
    feature_cols = get_feature_columns()
    for col in feature_cols:
        df = df.fillna(0, subset=[col])
    
    return df


def get_feature_columns():
    """
    Return list of engineered feature columns for KOL Trust Score ML training.
    
    Features designed to detect KOL không đáng tin (dùng fake followers, bot-like behavior).
    """
    return [
        # Log-transformed features (giảm skewness)
        "log_followers",
        "log_following", 
        "log_posts",
        "log_favorites",
        "log_account_age",
        
        # Capped ratios (clip outliers)
        "followers_following_ratio_capped",
        "posts_per_day_capped",
        
        # Derived features (business logic)
        "engagement_rate",
        "activity_score",
        "profile_completeness",
        "followers_per_day",
        "posts_per_follower",
        "following_per_day",
        "bio_length_norm",
        
        # Untrustworthy indicators (KOL dùng fake followers patterns)
        "high_activity_flag",           # Đăng quá nhiều → có thể dùng bot
        "low_engagement_high_posts",    # Nhiều posts nhưng ít engagement → fake followers
        "default_profile_score",        # KOL thật thường customize profile
        "suspicious_growth",            # Tăng followers bất thường → mua followers
        "fake_follower_indicator",      # Followers nhiều nhưng engagement thấp
        
        # Bins/Tiers (discretization)
        "followers_tier",
        "account_age_tier",
        "activity_tier",
        
        # Feature Interactions
        "verified_followers_interaction",
        "profile_engagement_interaction",
        "age_activity_interaction",
        
        # Binary features (original)
        "has_bio",
        "has_url",
        "has_profile_image",
        "verified",
    ]


def print_feature_stats(df):
    """Print statistics for engineered features."""
    print("\n" + "="*70)
    print("📈 ENGINEERED FEATURE STATISTICS")
    print("="*70)
    
    feature_cols = get_feature_columns()
    
    # Summary statistics
    print("\n📊 Numeric Feature Summary:")
    stats_df = df.select(feature_cols[:10]).describe()  # First 10 features
    stats_df.show(truncate=False)
    
    # Label distribution
    print("\n📊 Label Distribution:")
    df.groupBy("label").count().orderBy("label").show()
    
    # Feature count
    print(f"\n✅ Total Engineered Features: {len(feature_cols)}")


def save_features(df, output_format: str = "parquet"):
    """
    Save engineered features to MinIO.
    
    Ghi trực tiếp vào OUTPUT_PATH (không có timestamp subfolder) để Trino
    có thể đọc được với external_location đơn giản.
    
    Args:
        df: DataFrame with engineered features
        output_format: "parquet" or "json"
    """
    # Add metadata columns
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # Select columns to save
    feature_cols = get_feature_columns()
    meta_cols = ["kol_id", "label"]
    save_cols = meta_cols + feature_cols
    
    df_save = df.select(save_cols).withColumn(
        "_source", F.lit("feature_engineering")
    ).withColumn(
        "_processed_at", F.lit(timestamp)
    )
    
    # Ghi trực tiếp vào OUTPUT_PATH (overwrite toàn bộ)
    output_path = OUTPUT_PATH.rstrip("/") + "/"
    
    print(f"\n💾 Saving features to: {output_path}")
    print(f"   Format: {output_format}")
    print(f"   Columns: {len(save_cols) + 2}")
    
    if output_format == "parquet":
        df_save.write.mode("overwrite").parquet(output_path)
    else:
        df_save.write.mode("overwrite").json(output_path)
    
    # Count records saved
    count = df_save.count()
    print(f"   Records: {count:,}")
    
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Trust Score Feature Engineering with PySpark on Cluster"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Don't save, just show stats"
    )
    parser.add_argument(
        "--sample", 
        type=float, 
        default=1.0, 
        help="Sample fraction (0-1), e.g. 0.1 for 10%%"
    )
    parser.add_argument(
        "--output-format",
        choices=["parquet", "json"],
        default="parquet",
        help="Output format (default: parquet)"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run in local mode instead of cluster"
    )
    args = parser.parse_args()
    
    print("="*70)
    print("🚀 TRUST SCORE FEATURE ENGINEERING (PySpark Cluster)")
    print("="*70)
    print(f"  Input:  {INPUT_PATH}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Dry Run: {args.dry_run}")
    print(f"  Sample: {args.sample * 100:.0f}%")
    print(f"  Format: {args.output_format}")
    
    # Create Spark session
    master_url = "local[*]" if args.local else None
    spark = create_spark_session(master_url)
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Load data
        df = load_data(spark)
        
        # Sample if needed
        if args.sample < 1.0:
            df = df.sample(fraction=args.sample, seed=42)
            print(f"   Sampled: {df.count():,} records")
        
        # Feature Engineering
        df_engineered = feature_engineering(df)
        
        # Cache for multiple operations
        df_engineered.cache()
        
        # Print statistics
        print_feature_stats(df_engineered)
        
        # Print feature list
        feature_cols = get_feature_columns()
        print("\n" + "="*70)
        print(f"📋 ENGINEERED FEATURES ({len(feature_cols)} total)")
        print("="*70)
        for i, feat in enumerate(feature_cols, 1):
            print(f"  {i:2d}. {feat}")
        
        # Save
        if not args.dry_run:
            records = save_features(df_engineered, args.output_format)
            print(f"\n✅ Saved {records:,} records with {len(feature_cols)} features")
        else:
            print("\n🔍 DRY RUN - Not saving to storage")
        
        print("\n" + "="*70)
        print("✅ FEATURE ENGINEERING COMPLETE!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

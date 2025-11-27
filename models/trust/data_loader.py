"""
KOL TRUST SCORE - DATA LOADER
==============================

Load engineered features từ MinIO Parquet cho ML training.
Có thể chạy local (đọc từ MinIO) hoặc trên Spark cluster.

Usage:
------
# Local mode (Python + boto3)
python models/trust/data_loader.py

# Hoặc import trong training scripts
from models.trust.data_loader import load_training_data
X_train, X_test, y_train, y_test = load_training_data()
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# CONFIGURATION
# =============================================================================
# Support both direct endpoint and S3_ENDPOINT_URL (from docker-compose)
_s3_url = os.getenv("S3_ENDPOINT_URL", "")
if _s3_url:
    # Extract host:port from http://sme-minio:9000
    MINIO_ENDPOINT = _s3_url.replace("http://", "").replace("https://", "")
else:
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")

MINIO_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
MINIO_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", os.getenv("MINIO_SECRET_KEY", "minioadmin123"))
BUCKET = os.getenv("BUCKET", "kol-platform")

# Paths
FEATURES_PATH = f"gold/ml_trust_features_engineered/"
LOCAL_CACHE_PATH = PROJECT_ROOT / "data" / "ml_cache"

# Feature columns (31 features) - MUST match feature_engineering.py output
# Updated to match actual schema from ml_trust_features_engineered table
FEATURE_COLUMNS = [
    # Log-transformed features
    "log_followers",
    "log_following",
    "log_posts",
    "log_favorites",
    "log_account_age",
    
    # Ratio features (capped for outliers)
    "followers_following_ratio_capped",
    "posts_per_day_capped",
    "engagement_rate",
    
    # Behavioral scores
    "activity_score",
    "profile_completeness",
    "followers_per_day",
    "posts_per_follower",
    "following_per_day",
    "bio_length_norm",
    
    # Flag features (binary indicators)
    "high_activity_flag",
    "low_engagement_high_posts",
    "default_profile_score",
    "suspicious_growth",
    "fake_follower_indicator",
    
    # Categorical tiers (encoded)
    "followers_tier",
    "account_age_tier",
    "activity_tier",
    
    # Interaction features
    "verified_followers_interaction",
    "profile_engagement_interaction",
    "age_activity_interaction",
    
    # Binary profile features
    "has_bio",
    "has_url",
    "has_profile_image",
    "verified",
]

LABEL_COLUMN = "label"
ID_COLUMN = "kol_id"


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_from_minio_s3() -> pd.DataFrame:
    """
    Load data từ MinIO sử dụng boto3/s3fs.
    """
    import s3fs
    
    s3 = s3fs.S3FileSystem(
        key=MINIO_ACCESS_KEY,
        secret=MINIO_SECRET_KEY,
        endpoint_url=f"http://{MINIO_ENDPOINT}",
        use_ssl=False
    )
    
    path = f"{BUCKET}/{FEATURES_PATH}"
    print(f"📥 Loading from MinIO: s3://{path}")
    
    # Read all parquet files
    files = s3.glob(f"{path}*.parquet")
    if not files:
        files = s3.glob(f"{path}**/*.parquet")
    
    print(f"   Found {len(files)} parquet files")
    
    dfs = []
    for f in files:
        with s3.open(f, 'rb') as file:
            df = pd.read_parquet(file)
            dfs.append(df)
    
    df = pd.concat(dfs, ignore_index=True)
    print(f"   Loaded {len(df):,} records")
    
    return df


def load_from_local_cache() -> pd.DataFrame:
    """
    Load từ local cache nếu đã download.
    """
    cache_file = LOCAL_CACHE_PATH / "ml_trust_features.parquet"
    
    if cache_file.exists():
        print(f"📂 Loading from cache: {cache_file}")
        df = pd.read_parquet(cache_file)
        print(f"   Loaded {len(df):,} records from cache")
        return df
    
    return None


def save_to_local_cache(df: pd.DataFrame):
    """
    Cache data locally để không cần load lại từ MinIO.
    """
    LOCAL_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    cache_file = LOCAL_CACHE_PATH / "ml_trust_features.parquet"
    
    df.to_parquet(cache_file, index=False)
    print(f"💾 Cached to: {cache_file}")


def load_features_dataframe(use_cache: bool = True) -> pd.DataFrame:
    """
    Load features DataFrame từ cache hoặc MinIO.
    
    Args:
        use_cache: Sử dụng local cache nếu có
        
    Returns:
        DataFrame với features và labels
    """
    # Try cache first
    if use_cache:
        df = load_from_local_cache()
        if df is not None:
            return df
    
    # Load from MinIO - prefer PyArrow (always available in container)
    # s3fs is optional, PyArrow fs.S3FileSystem works reliably
    try:
        df = load_from_minio_pyarrow()
        
        # Cache for next time
        if use_cache:
            save_to_local_cache(df)
        
        return df
    except Exception as e:
        print(f"⚠️ PyArrow method failed: {e}")
        print("   Trying s3fs method...")
        
        # Fallback: use s3fs if available
        return load_from_minio_s3()


def load_from_minio_pyarrow() -> pd.DataFrame:
    """
    Alternative loading method using pyarrow + fsspec.
    """
    import pyarrow.parquet as pq
    from pyarrow import fs
    
    s3_fs = fs.S3FileSystem(
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        endpoint_override=MINIO_ENDPOINT,
        scheme="http"
    )
    
    path = f"{BUCKET}/{FEATURES_PATH}"
    print(f"📥 Loading via PyArrow: {path}")
    
    table = pq.read_table(path, filesystem=s3_fs)
    df = table.to_pandas()
    print(f"   Loaded {len(df):,} records")
    
    return df


# =============================================================================
# DATA PREPARATION FOR ML
# =============================================================================

def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Prepare X (features) và y (labels) từ DataFrame.
    
    Returns:
        X: DataFrame với feature columns
        y: Series với labels
    """
    # Validate columns exist
    missing_features = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing_features:
        print(f"⚠️ Missing features: {missing_features}")
        available = [c for c in FEATURE_COLUMNS if c in df.columns]
        print(f"   Using {len(available)} available features")
        feature_cols = available
    else:
        feature_cols = FEATURE_COLUMNS
    
    X = df[feature_cols].copy()
    y = df[LABEL_COLUMN].copy()
    
    # Handle missing values
    null_counts = X.isnull().sum()
    if null_counts.any():
        print(f"⚠️ Null values found:")
        for col in null_counts[null_counts > 0].index:
            print(f"   {col}: {null_counts[col]:,} nulls")
        
        # Fill with median for numeric columns
        X = X.fillna(X.median())
    
    # Handle infinities
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median())
    
    print(f"✅ Prepared {X.shape[0]:,} samples × {X.shape[1]} features")
    print(f"   Label distribution: {y.value_counts().to_dict()}")
    
    return X, y


def load_training_data(
    test_size: float = 0.2,
    random_state: int = 42,
    stratify: bool = True,
    use_cache: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Load và split data thành train/test sets.
    
    Args:
        test_size: Tỷ lệ test set (default 20%)
        random_state: Random seed for reproducibility
        stratify: Stratified split để giữ tỷ lệ labels
        use_cache: Sử dụng local cache
        
    Returns:
        X_train, X_test, y_train, y_test
    """
    print("="*60)
    print("🚀 LOADING ML TRAINING DATA")
    print("="*60)
    
    # Load data
    df = load_features_dataframe(use_cache=use_cache)
    
    # Prepare features
    X, y = prepare_features(df)
    
    # Split
    stratify_param = y if stratify else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, 
        test_size=test_size, 
        random_state=random_state,
        stratify=stratify_param
    )
    
    print(f"\n📊 Data Split:")
    print(f"   Train: {len(X_train):,} samples")
    print(f"   Test:  {len(X_test):,} samples")
    print(f"   Train label dist: {y_train.value_counts().to_dict()}")
    print(f"   Test label dist:  {y_test.value_counts().to_dict()}")
    
    return X_train, X_test, y_train, y_test


def get_feature_names() -> list[str]:
    """Return list of feature names."""
    return FEATURE_COLUMNS.copy()


def get_class_weights(y: pd.Series) -> dict:
    """
    Calculate class weights for imbalanced data.
    
    Returns:
        Dict mapping class label to weight
    """
    from sklearn.utils.class_weight import compute_class_weight
    
    classes = np.unique(y)
    weights = compute_class_weight('balanced', classes=classes, y=y)
    
    return dict(zip(classes, weights))


def get_scale_pos_weight(y: pd.Series) -> float:
    """
    Calculate scale_pos_weight for XGBoost.
    
    Formula: sum(negative) / sum(positive)
    """
    n_neg = (y == 0).sum()
    n_pos = (y == 1).sum()
    
    return n_neg / n_pos


# =============================================================================
# DATA QUALITY CHECK
# =============================================================================

def check_data_quality(df: pd.DataFrame) -> dict:
    """
    Run data quality checks.
    """
    print("\n" + "="*60)
    print("🔍 DATA QUALITY CHECK")
    print("="*60)
    
    report = {
        "total_records": len(df),
        "total_features": len(FEATURE_COLUMNS),
        "missing_features": [],
        "null_counts": {},
        "label_distribution": {},
        "feature_stats": {}
    }
    
    # Check missing features
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        print(f"❌ Missing features: {missing}")
        report["missing_features"] = missing
    else:
        print(f"✅ All {len(FEATURE_COLUMNS)} features present")
    
    # Check nulls
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            nulls = df[col].isnull().sum()
            if nulls > 0:
                report["null_counts"][col] = nulls
                print(f"⚠️ {col}: {nulls:,} nulls ({100*nulls/len(df):.2f}%)")
    
    if not report["null_counts"]:
        print("✅ No null values")
    
    # Label distribution
    if LABEL_COLUMN in df.columns:
        dist = df[LABEL_COLUMN].value_counts().to_dict()
        report["label_distribution"] = dist
        print(f"\n📊 Label Distribution:")
        for label, count in sorted(dist.items()):
            pct = 100 * count / len(df)
            label_name = "Trustworthy" if label == 0 else "Untrustworthy"
            print(f"   {label} ({label_name}): {count:,} ({pct:.1f}%)")
    
    # Feature statistics summary
    print(f"\n📈 Feature Statistics (sample):")
    sample_features = ["followers_count", "engagement_score", "fake_follower_indicator"]
    for feat in sample_features:
        if feat in df.columns:
            col = df[feat]
            print(f"   {feat}:")
            print(f"      mean={col.mean():.4f}, std={col.std():.4f}")
            print(f"      min={col.min():.4f}, max={col.max():.4f}")
    
    return report


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point - load and validate data."""
    print("="*70)
    print("🔬 KOL TRUST SCORE - DATA LOADER")
    print("="*70)
    
    # Try to load data
    try:
        df = load_features_dataframe(use_cache=True)
        
        # Quality check
        report = check_data_quality(df)
        
        # Prepare for ML
        X, y = prepare_features(df)
        
        # Show class imbalance info
        print(f"\n📊 Class Imbalance Info:")
        weights = get_class_weights(y)
        print(f"   Class weights: {weights}")
        print(f"   scale_pos_weight (XGBoost): {get_scale_pos_weight(y):.4f}")
        
        print("\n" + "="*70)
        print("✅ DATA READY FOR ML TRAINING!")
        print("="*70)
        print(f"\nNext steps:")
        print(f"  1. python models/trust/train_xgb.py")
        print(f"  2. python models/trust/train_lgbm.py")
        print(f"  3. python models/trust/score_iforest.py")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n💡 Troubleshooting:")
        print("   1. Ensure MinIO is running: docker ps | grep minio")
        print("   2. Check MINIO_ENDPOINT environment variable")
        print("   3. Run feature engineering first if needed")
        sys.exit(1)


if __name__ == "__main__":
    main()

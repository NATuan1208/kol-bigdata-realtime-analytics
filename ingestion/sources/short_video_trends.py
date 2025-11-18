"""
Vietnamese Social Media Dataset Collector - PHASE 1B
====================================================

Collects large-scale Vietnamese social media datasets from CSV/JSON sources.

✨ NEW in Phase 1B: Primary source for reaching 10k-50k records target.

Data Sources:
- Local CSV files with Vietnamese social media posts
- Kaggle Vietnamese social media datasets
- Vietnamese influencer/KOL databases
- Public Vietnamese social network data

Target: 5,000 - 100,000 records

Typical CSV Format:
- user_id: Unique user identifier
- username: Display name
- text/content: Post text content
- likes/reactions: Engagement metrics
- comments: Number of comments
- shares: Number of shares  
- created_at: Timestamp
- platform: Source platform (Facebook, Zalo, TikTok Vietnam)

Output: Normalized records with kol_id=user_id, platform=vietnamese_social
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd

try:
    from datasets import load_dataset
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not HUGGINGFACE_AVAILABLE:
    logger.warning("⚠️  HuggingFace datasets not installed. Install with: pip install datasets")

# Default paths for Vietnamese datasets
DEFAULT_DATASET_PATHS = [
    "data/vietnamese/social_media.csv",
    "data/vietnamese/influencers.csv",
    "data/vietnamese/facebook_vietnam.csv",
    "data/vietnamese/zalo_posts.csv",
    "data/vietnamese/tiktok_vietnam.csv"
]


def load_vietnamese_csv(file_path: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Load Vietnamese social media dataset from CSV.
    
    Args:
        file_path: Path to CSV file
        limit: Maximum rows to load
        
    Returns:
        DataFrame with loaded data
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If CSV is invalid
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset not found: {file_path}")
    
    try:
        logger.info(f"📂 Loading: {file_path}")
        
        # Try UTF-8 first, then fallback to cp1252 for Vietnamese
        try:
            df = pd.read_csv(file_path, encoding='utf-8', nrows=limit)
        except UnicodeDecodeError:
            logger.info("   Retrying with cp1252 encoding...")
            df = pd.read_csv(file_path, encoding='cp1252', nrows=limit)
        
        logger.info(f"   ✅ Loaded {len(df)} rows, {len(df.columns)} columns")
        logger.info(f"   Columns: {', '.join(df.columns[:5])}{'...' if len(df.columns) > 5 else ''}")
        
        return df
        
    except Exception as e:
        logger.error(f"   ❌ Failed to load CSV: {e}")
        raise ValueError(f"Invalid CSV file: {file_path}") from e


def load_huggingface_dataset(dataset_name: str, split: str = "train", limit: Optional[int] = None, data_files: Optional[str] = None) -> pd.DataFrame:
    """
    Load dataset from HuggingFace Hub.
    
    ✨ PHASE 1B: HuggingFace integration for large-scale real datasets.
    
    Args:
        dataset_name: HuggingFace dataset identifier (e.g., "TarekMasryo/YouTube-Shorts-TikTok-Trends-2025")
        split: Dataset split to load (default: "train")
        limit: Maximum number of rows to load
        data_files: Specific data file to load (e.g., "data/youtube_shorts_tiktok_trends_2025.csv")
    
    Returns:
        DataFrame with loaded data
        
    Raises:
        ImportError: If HuggingFace datasets not installed
        
    Examples:
        >>> df = load_huggingface_dataset("TarekMasryo/YouTube-Shorts-TikTok-Trends-2025", 
        ...                               data_files="data/youtube_shorts_tiktok_trends_2025.csv", 
        ...                               limit=10000)
    """
    if not HUGGINGFACE_AVAILABLE:
        raise ImportError(
            "HuggingFace datasets not installed. Install with: pip install datasets"
        )
    
    logger.info(f"📥 Loading HuggingFace dataset: {dataset_name}")
    logger.info(f"   Split: {split}")
    if data_files:
        logger.info(f"   Data files: {data_files}")
    
    try:
        ds = load_dataset(dataset_name, split=split, data_files=data_files)
        df = ds.to_pandas()
        
        logger.info(f"   ✅ Loaded {len(df):,} rows from HuggingFace")
        logger.info(f"   📊 Columns ({len(df.columns)}): {', '.join(df.columns[:8])}{'...' if len(df.columns) > 8 else ''}")
        
        if limit and len(df) > limit:
            df = df.head(limit)
            logger.info(f"   ✂️  Limited to {limit:,} rows")
        
        return df
        
    except Exception as e:
        logger.error(f"   ❌ Failed to load HuggingFace dataset: {e}")
        raise


def normalize_vietnamese_record(row: pd.Series, source_file: str, source_tag: str = "vietnam_social") -> Dict[str, Any]:
    """
    Normalize Vietnamese social media record to canonical format.
    
    Canonical format:
    {
        kol_id: user_id or username,
        platform: "vietnamese_social",
        source: "vietnam_social",
        payload: {...},  # All columns from CSV
        ingest_ts: ISO timestamp
    }
    
    Args:
        row: DataFrame row
        source_file: Source filename for tracking
        
    Returns:
        Normalized record ready for Bronze layer
    """
    # Extract KOL ID (try multiple column names including HuggingFace schema)
    kol_id = None
    for col in ['user_id', 'username', 'id', 'account_id', 'creator_id', 'author_handle', 'row_id']:
        if col in row.index and pd.notna(row[col]):
            kol_id = str(row[col])
            break
    
    if not kol_id:
        kol_id = f"unknown_{hash(str(row.values))}"
    
    # Extract platform (support HuggingFace "platform" column)
    platform = "vietnamese_social"
    if 'platform' in row.index and pd.notna(row['platform']):
        platform = str(row['platform']).lower()
    
    # Build payload with all columns
    payload = {}
    for key, value in row.items():
        # Convert NaN to None for JSON serialization
        if pd.isna(value):
            payload[key] = None
        else:
            payload[key] = value
    
    # Add metadata
    payload["_source_file"] = os.path.basename(source_file)
    payload["_fetch_time"] = datetime.utcnow().isoformat()
    
    return {
        "kol_id": kol_id,
        "platform": platform,
        "source": source_tag,
        "payload": payload,
        "ingest_ts": datetime.utcnow().isoformat()
    }


def create_sample_vietnamese_dataset(output_path: str = "data/vietnamese/sample_social.csv", num_rows: int = 100000) -> str:
    """
    Create sample Vietnamese social media CSV (fallback).
    
    ✨ PHASE 1B: Scale up to 100,000 rows for realistic dataset size.
    
    Args:
        output_path: Where to save sample CSV
        num_rows: Number of rows to generate (default: 100k)
        
    Returns:
        Path to created file
    """
    logger.info(f"📝 Creating Vietnamese sample dataset with {num_rows:,} rows...")
    
    # Base patterns (will repeat to reach num_rows)
    base_size = 5
    num_repeats = num_rows // base_size
    
    sample_data = {
        "user_id": ["vnuser001", "vnuser002", "vnuser003", "vnuser004", "vnuser005"] * num_repeats,
        "username": ["Nguyen Van A", "Tran Thi B", "Le Van C", "Pham Thi D", "Hoang Van E"] * num_repeats,
        "text": [
            "Hôm nay thời tiết đẹp quá! #Vietnam #Saigon",
            "Review quán cà phê mới ở Hà Nội 🇻🇳 ☕",
            "Món ăn Việt Nam ngon tuyệt vời!",
            "Du lịch Đà Nẵng cuối tuần này 🏖️",
            "Chia sẻ kinh nghiệm học tiếng Anh"
        ] * num_repeats,
        "likes": [1250, 890, 2340, 567, 1890] * num_repeats,
        "comments": [45, 23, 89, 12, 67] * num_repeats,
        "shares": [12, 5, 34, 3, 18] * num_repeats,
        "created_at": [
            "2025-11-15 10:30:00",
            "2025-11-15 14:20:00",
            "2025-11-16 09:15:00",
            "2025-11-16 16:45:00",
            "2025-11-17 08:00:00"
        ] * num_repeats,
        "platform": ["Facebook", "Zalo", "TikTok", "Facebook", "Zalo"] * num_repeats,
        "location": ["Ho Chi Minh City", "Hanoi", "Da Nang", "Can Tho", "Hai Phong"] * num_repeats
    }
    
    df = pd.DataFrame(sample_data)
    
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"   💾 Writing {len(df):,} rows to CSV...")
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"   ✅ Created: {output_path}")
    logger.info(f"   📊 Size: {file_size_mb:.2f} MB ({len(df):,} rows)")
    
    return output_path


def collect(
    csv_paths: Optional[List[str]] = None,
    limit: Optional[int] = None,
    create_sample: bool = True,
    huggingface_dataset: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Main collection function for Vietnamese social media data.
    
    ✨ PHASE 1B: Primary source for 5k-100k records.
    
    PRIORITY FLOW:
    1. Load from HuggingFace dataset (if specified) - **NEW in Phase 1B**
    2. Try loading from provided CSV paths
    3. Try default dataset locations
    4. Create sample dataset if enabled (100,000 rows)
    
    Args:
        csv_paths: List of CSV file paths to load
        limit: Maximum records to collect (per file)
        create_sample: Whether to create sample data if no files found
        huggingface_dataset: HuggingFace dataset name (e.g., "TarekMasryo/YouTube-Shorts-TikTok-Trends-2025")
        
    Returns:
        List of normalized records ready for Bronze layer
        
    Phase 1B Examples:
        # Load from HuggingFace (48,079 YouTube Shorts + TikTok trends)
        >>> records = collect(huggingface_dataset="TarekMasryo/YouTube-Shorts-TikTok-Trends-2025", limit=50000)
        
        # Load from specific files
        >>> records = collect(csv_paths=['data/vietnamese/fb_posts.csv'], limit=10000)
        
        # Use default paths (auto-discover)
        >>> records = collect(limit=50000)
        
        # Create sample for testing (100k records)
        >>> records = collect(create_sample=True, limit=5000)
    """
    logger.info("=" * 70)
    logger.info("🇻🇳 PHASE 1B: VIETNAMESE SOCIAL MEDIA COLLECTION")
    logger.info("=" * 70)
    
    all_records = []
    files_processed = 0
    
    # PRIORITY 1: HuggingFace dataset (NEW in Phase 1B)
    if huggingface_dataset:
        logger.info(f"📥 HuggingFace Priority: {huggingface_dataset}")
        logger.info("")
        
        try:
            # Load main video-level file (48,079 rows)
            df = load_huggingface_dataset(
                huggingface_dataset, 
                limit=limit,
                data_files="data/youtube_shorts_tiktok_trends_2025.csv"
            )
            
            # Normalize records
            logger.info("🔄 Normalizing HuggingFace records...")
            for idx, row in df.iterrows():
                try:
                    record = normalize_vietnamese_record(row, f"huggingface_{huggingface_dataset.split('/')[-1]}", source_tag="short_video_trends")
                    all_records.append(record)
                except Exception as e:
                    logger.warning(f"   Skipped row {idx}: {e}")
                    continue
            
            logger.info(f"   ✅ Normalized {len(all_records):,} HuggingFace records")
            logger.info("")
            
            # Summary
            logger.info("=" * 70)
            logger.info("📊 HUGGINGFACE COLLECTION SUMMARY")
            logger.info("=" * 70)
            logger.info(f"   Dataset: {huggingface_dataset}")
            logger.info(f"   Total records: {len(all_records):,}")
            
            # Show platform breakdown if available
            if 'platform' in df.columns:
                platform_counts = df['platform'].value_counts()
                logger.info(f"   Platform breakdown:")
                for platform, count in platform_counts.head(5).items():
                    logger.info(f"      {platform}: {count:,}")
            
            logger.info("=" * 70)
            logger.info("")
            
            return all_records
            
        except Exception as e:
            logger.error(f"❌ HuggingFace loading failed: {e}")
            logger.info("   Falling back to CSV sources...")
            logger.info("")
    
    # PRIORITY 2 & 3: CSV files (existing logic)
    # Collect paths to try
    paths_to_try = []
    
    if csv_paths:
        paths_to_try.extend(csv_paths)
    else:
        # Try default paths
        paths_to_try.extend(DEFAULT_DATASET_PATHS)
    
    # Filter to existing files
    existing_files = [p for p in paths_to_try if os.path.exists(p)]
    
    if not existing_files and create_sample:
        logger.info("📝 No Vietnamese datasets found, creating sample data...")
        logger.info("   🎯 Target: 100,000 rows for Phase 1B")
        sample_path = create_sample_vietnamese_dataset(num_rows=100000)
        existing_files = [sample_path]
    
    if not existing_files:
        logger.warning("⚠️  No Vietnamese datasets available")
        logger.warning(f"   Tried: {', '.join(paths_to_try[:3])}...")
        logger.warning(f"   Place CSV files in data/vietnamese/ or enable create_sample=True")
        return []
    
    logger.info(f"📂 Found {len(existing_files)} dataset file(s)")
    logger.info("")
    
    # Process each file
    for file_path in existing_files:
        try:
            logger.info(f"🔍 Processing: {os.path.basename(file_path)}")
            
            df = load_vietnamese_csv(file_path, limit=limit)
            
            # Normalize records
            file_records = []
            for _, row in df.iterrows():
                try:
                    record = normalize_vietnamese_record(row, file_path, source_tag="vietnam_social")
                    file_records.append(record)
                except Exception as e:
                    logger.warning(f"   Skipped row: {e}")
                    continue
            
            all_records.extend(file_records)
            files_processed += 1
            
            logger.info(f"   ✅ Collected {len(file_records)} records from {os.path.basename(file_path)}")
            logger.info("")
            
        except Exception as e:
            logger.error(f"   ❌ Failed to process {file_path}: {e}")
            continue
    
    # Summary
    logger.info("=" * 70)
    logger.info("📊 VIETNAMESE SOCIAL COLLECTION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"   Files processed: {files_processed}/{len(existing_files)}")
    logger.info(f"   Total records: {len(all_records):,}")
    logger.info("=" * 70)
    logger.info("")
    
    return all_records


if __name__ == "__main__":
    # Self-test
    logger.info("\n" + "=" * 70)
    logger.info("🧪 TESTING VIETNAMESE SOCIAL MEDIA COLLECTOR")
    logger.info("=" * 70)
    
    # Test 1: Create and load sample data
    logger.info("\n--- Test 1: Sample Data (5,000 records) ---")
    records = collect(create_sample=True, limit=100)
    if records:
        logger.info(f"✅ SUCCESS: {len(records)} records collected")
        logger.info(f"   Sample KOL: {records[0]['kol_id']}")
        logger.info(f"   Sample text: {records[0]['payload'].get('text', 'N/A')[:60]}...")
    
    # Test 2: Try loading from default paths
    logger.info("\n--- Test 2: Default Paths ---")
    for path in DEFAULT_DATASET_PATHS[:3]:
        if os.path.exists(path):
            logger.info(f"   ✅ Found: {path}")
        else:
            logger.info(f"   ⚠️  Not found: {path}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ VIETNAMESE SOCIAL COLLECTOR TESTS COMPLETE")
    logger.info("=" * 70 + "\n")

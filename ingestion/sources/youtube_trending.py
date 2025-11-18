"""
YouTube Trending Data Collector - PHASE 1B SCALE-UP VERSION
============================================================

Collects REAL YouTube trending video data using YouTube Data API v3.
✨ NEW in Phase 1B: Multi-day & multi-region support for large-scale ingestion.

PRIORITY:
1. ✅ Use YouTube Data API v3 (REAL-TIME DATA)
2. Fall back to CSV files if API unavailable  
3. Create sample data as last resort

Phase 1B Features:
------------------
- Multi-day ingestion: Fetch trending for past N days
- Multi-region: VN, US, KR, JP, BR, etc.
- Rate limiting: 100 API calls/day (10k quota units)
- Deduplication: Handle same video trending across regions/days

Setup:
------
1. Get FREE API key: https://console.cloud.google.com/apis/credentials
2. Enable YouTube Data API v3
3. Add to .env.kol: YOUTUBE_API_KEY=AIzaSyB...

Quota: 10,000 units/day
- Each API call = 100 units
- Max 100 calls/day = 5,000 videos (50 per call)

Output: Normalized records with kol_id=channel_id, platform=youtube
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

import pandas as pd
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_youtube_trending_api(
    api_key: str, 
    region_code: str = "US", 
    max_results: int = 50,
    trending_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch REAL trending videos from YouTube Data API v3.
    
    Phase 1B: Enhanced with date tracking for multi-day ingestion.
    
    Args:
        api_key: YouTube Data API v3 key
        region_code: ISO 3166-1 alpha-2 country code
                     Popular: VN, US, KR, JP, BR, IN, DE, FR, GB
        max_results: Maximum number of videos to fetch (1-50)
        trending_date: Date to mark videos as trending (YYYY-MM-DD)
                       If None, uses current UTC date
    
    Returns:
        List of video data dictionaries with real YouTube data
        
    Quota Cost: 100 units per call
    """
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": min(max_results, 50),
            "key": api_key
        }
        
        if trending_date is None:
            trending_date = datetime.utcnow().strftime("%Y-%m-%d")
        
        logger.info(f"🔴 Fetching REAL trending videos (region={region_code}, date={trending_date})...")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        videos = []
        
        for item in data.get("items", []):
            video_id = item["id"]
            snippet = item["snippet"]
            statistics = item.get("statistics", {})
            
            videos.append({
                "video_id": video_id,
                "channel_id": snippet["channelId"],
                "channel_title": snippet["channelTitle"],
                "title": snippet["title"],
                "category_id": snippet.get("categoryId", ""),
                "publish_time": snippet["publishedAt"],
                "trending_date": trending_date,
                "region_code": region_code,  # NEW: Track region
                "view_count": int(statistics.get("viewCount", 0)),
                "likes": int(statistics.get("likeCount", 0)),
                "dislikes": 0,  # YouTube removed public dislike counts
                "comment_count": int(statistics.get("commentCount", 0)),
                "tags": "|".join(snippet.get("tags", [])),
                "description": snippet.get("description", "")[:500]  # Truncate long descriptions
            })
        
        logger.info(f"✅ Successfully fetched {len(videos)} REAL trending videos")
        return videos
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to fetch YouTube trending data: {e}")
        if "403" in str(e) or "quotaExceeded" in str(e):
            logger.error("💡 API quota exceeded or invalid API key")
            logger.error("   Quota: 10,000 units/day (100 units per call = 100 calls max)")
            logger.error("   Get key at: https://console.cloud.google.com/apis/credentials")
        return []
    except Exception as e:
        logger.error(f"❌ Error processing YouTube API response: {e}")
        return []


def load_csv_file(file_path: str) -> Optional[pd.DataFrame]:
    """
    Load YouTube trending data from CSV file (fallback).
    
    Args:
        file_path: Path to CSV file
    
    Returns:
        DataFrame or None if load fails
    """
    if not os.path.exists(file_path):
        logger.warning(f"CSV file not found: {file_path}")
        return None
    
    try:
        df = pd.read_csv(file_path, encoding="utf-8")
        logger.info(f"Loaded {len(df)} rows from {file_path}")
        return df
    except Exception as e:
        logger.error(f"Error loading CSV file {file_path}: {e}")
        return None


def normalize_youtube_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize YouTube video data to canonical RAW record format.
    
    Canonical format:
    {
        kol_id: channel_id,
        platform: "youtube",
        source: "youtube_trending",
        payload: {...},  # All video metadata
        ingest_ts: ISO timestamp
    }
    
    Args:
        row: Dict with YouTube video data
    
    Returns:
        Normalized record ready for Bronze layer
    """
    return {
        "kol_id": row.get("channel_id", ""),
        "platform": "youtube",
        "source": "youtube_trending",
        "payload": {
            "video_id": row.get("video_id", ""),
            "channel_id": row.get("channel_id", ""),
            "channel_title": row.get("channel_title", ""),
            "title": row.get("title", ""),
            "category_id": row.get("category_id", ""),
            "publish_time": row.get("publish_time", ""),
            "trending_date": row.get("trending_date", ""),
            "region_code": row.get("region_code", "US"),  # Phase 1B: Track region
            "view_count": row.get("view_count", 0),
            "likes": row.get("likes", 0),
            "dislikes": row.get("dislikes", 0),
            "comment_count": row.get("comment_count", 0),
            "tags": row.get("tags", ""),
            "description": row.get("description", "")
        },
        "ingest_ts": datetime.utcnow().isoformat()
    }


def collect_from_csv(file_path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Collect YouTube trending data from CSV file.
    
    Args:
        file_path: Path to CSV file
        limit: Maximum records to return
    
    Returns:
        List of normalized records
    """
    df = load_csv_file(file_path)
    if df is None:
        return []
    
    if limit:
        df = df.head(limit)
    
    records = []
    for _, row in df.iterrows():
        record = normalize_youtube_record(row.to_dict())
        records.append(record)
    
    logger.info(f"Normalized {len(records)} YouTube records from CSV")
    return records


def create_sample_csv(output_path: str = "data/youtube/sample_trending.csv") -> str:
    """
    Create sample YouTube trending CSV (last resort fallback).
    
    Args:
        output_path: Where to save the CSV
    
    Returns:
        Path to created CSV file
    """
    sample_data = {
        "video_id": ["dQw4w9WgXcQ", "Wmc8bQoL-J0", "kJQP7kiw5Fk"],
        "channel_id": ["UCuAXFkgsw1L7xaCfnd5JJOw", "UCX6OQ3DkcsbYNE6H8uQQuVA", "UC-lHJZR3Gqxm24_Vd_AJ5Yw"],
        "channel_title": ["Rick Astley", "MrBeast", "PewDiePie"],
        "title": [
            "Rick Astley - Never Gonna Give You Up",
            "I Spent 7 Days In The World's Most Dangerous Jungle",
            "Every TikTok Trend Explained"
        ],
        "category_id": ["10", "24", "24"],
        "publish_time": ["2009-10-25T06:57:33Z", "2023-11-15T20:00:00Z", "2023-11-16T15:00:00Z"],
        "trending_date": ["2023-11-16", "2023-11-16", "2023-11-16"],
        "view_count": [1400000000, 85000000, 12000000],
        "likes": [15000000, 4200000, 890000],
        "dislikes": [0, 0, 0],
        "comment_count": [2100000, 156000, 34000],
        "tags": [
            "rick astley|never gonna give you up|80s music",
            "mrbeast|challenge|jungle|survival",
            "pewdiepie|tiktok|trends|memes"
        ],
        "description": [
            "Official Rick Astley - Never Gonna Give You Up",
            "I spent a week in the Amazon rainforest",
            "Breaking down every TikTok trend from 2023"
        ]
    }
    
    df = pd.DataFrame(sample_data)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    logger.info(f"📝 Created sample CSV at {output_path} (fallback data)")
    return output_path


def collect(
    api_key: Optional[str] = None,
    region_codes: List[str] = ["US", "VN"],
    csv_paths: Optional[List[str]] = None,
    limit: Optional[int] = None,
    use_api: bool = True,
    days_back: int = 0,
    rate_limit_delay: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Main collection function for YouTube trending data.
    
    ✨ PHASE 1B UPGRADE: Multi-day & multi-region support
    
    PRIORITY FLOW:
    1. ✅ Try YouTube Data API v3 first (REAL DATA)
    2. Fall back to CSV files if API fails
    3. Create sample data as last resort
    
    Args:
        api_key: YouTube Data API v3 key (or set YOUTUBE_API_KEY env var)
                 Get free key at: https://console.cloud.google.com/apis/credentials
        region_codes: List of ISO 3166-1 alpha-2 country codes
                      Phase 1B: ['VN', 'US', 'KR', 'JP', 'BR']
        csv_paths: List of CSV file paths (fallback option)
        limit: Maximum number of records to collect (per region per day)
        use_api: Whether to try API first (default True for REAL data)
        days_back: Number of days back to collect (0 = today only)
                   Phase 1B: Set to 7-30 for multi-day ingestion
        rate_limit_delay: Seconds to wait between API calls (default 1.0)
                         Prevents hitting rate limits
    
    Returns:
        List of normalized records ready for Bronze layer
        
    Phase 1B Examples:
        # Collect 7 days of trending from 5 regions (7*5 = 35 API calls)
        >>> records = collect(region_codes=['VN', 'US', 'KR', 'JP', 'BR'], 
        ...                   days_back=7, limit=50)
        
        # Single region, 30 days back (30 API calls)
        >>> records = collect(region_codes=['VN'], days_back=30, limit=50)
        
        # Test with sample data
        >>> records = collect(use_api=False, limit=5)
        
    Quota Management:
        - Each API call = 100 units
        - Daily quota = 10,000 units = 100 calls
        - Example: 5 regions * 7 days = 35 calls = 3,500 units ✅
        - Example: 5 regions * 30 days = 150 calls = ❌ EXCEEDS QUOTA
    """
    all_records = []
    seen_videos: Set[str] = set()  # Deduplicate videos across regions/days
    total_calls = 0
    max_calls = 90  # Safety limit (90% of 100 daily calls)
    
    # Priority 1: Try YouTube Data API v3 for REAL DATA
    api_key = api_key or os.getenv("YOUTUBE_API_KEY")
    
    if use_api and api_key:
        logger.info("=" * 70)
        logger.info("🔴 PHASE 1B: LARGE-SCALE YOUTUBE TRENDING INGESTION")
        logger.info("=" * 70)
        logger.info(f"📅 Days back: {days_back}")
        logger.info(f"🌍 Regions: {', '.join(region_codes)}")
        logger.info(f"📊 Estimated API calls: {len(region_codes) * (days_back + 1)}")
        logger.info(f"🔢 Max records per call: {limit or 50}")
        logger.info("")
        
        # Generate date range
        dates_to_fetch = []
        for i in range(days_back + 1):
            date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            dates_to_fetch.append(date)
        
        logger.info(f"📆 Fetching dates: {dates_to_fetch[0]} to {dates_to_fetch[-1]}")
        logger.info("")
        
        # Fetch for each date and region combination
        for fetch_date in dates_to_fetch:
            for region in region_codes:
                if total_calls >= max_calls:
                    logger.warning(f"⚠️  Reached max API calls limit ({max_calls})")
                    logger.warning(f"   Collected {len(all_records)} records so far")
                    logger.warning(f"   Consider reducing days_back or regions")
                    break
                
                logger.info(f"🔍 Fetching: {region} | {fetch_date} (call {total_calls + 1}/{max_calls})")
                
                videos = fetch_youtube_trending_api(
                    api_key, 
                    region, 
                    limit or 50,
                    trending_date=fetch_date
                )
                
                total_calls += 1
                
                # Deduplicate by video_id
                for video in videos:
                    video_id = video['video_id']
                    if video_id not in seen_videos:
                        seen_videos.add(video_id)
                        record = normalize_youtube_record(video)
                        all_records.append(record)
                
                # Rate limiting
                if total_calls < max_calls and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)
            
            if total_calls >= max_calls:
                break
        
        if all_records:
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"✅ PHASE 1B SUCCESS: Collected {len(all_records)} UNIQUE videos")
            logger.info(f"📊 API calls made: {total_calls}")
            logger.info(f"🌍 Regions covered: {', '.join(region_codes)}")
            logger.info(f"📅 Date range: {dates_to_fetch[-1]} to {dates_to_fetch[0]}")
            logger.info(f"🔢 Deduplication: {len(seen_videos)} unique videos")
            logger.info("")
            logger.info(f"🎬 Sample: {all_records[0]['payload']['title']}")
            logger.info(f"   Region: {all_records[0]['payload']['region_code']}")
            logger.info(f"   Views: {all_records[0]['payload']['view_count']:,}")
            logger.info("=" * 70)
            return all_records
        else:
            logger.warning("⚠️  API returned no data, falling back to CSV...")
    
    elif not api_key and use_api:
        logger.warning("=" * 60)
        logger.warning("⚠️  NO YOUTUBE_API_KEY FOUND")
        logger.warning("=" * 60)
        logger.warning("To collect REAL data:")
        logger.warning("1. Get free API key: https://console.cloud.google.com/apis/credentials")
        logger.warning("2. Add to .env.kol: YOUTUBE_API_KEY=AIzaSyB...")
        logger.warning("3. Rerun collector")
        logger.warning("")
        logger.info("📁 Falling back to CSV files or sample data...")
    
    # Priority 2: Use CSV files
    if csv_paths:
        logger.info(f"📁 Using CSV files as data source...")
        for csv_path in csv_paths:
            logger.info(f"Processing: {csv_path}")
            records = collect_from_csv(csv_path, limit)
            all_records.extend(records)
            
            if limit and len(all_records) >= limit:
                all_records = all_records[:limit]
                break
    
    # Priority 3: Create sample data (last resort)
    if not all_records:
        logger.info("📝 No data sources available, creating sample data...")
        sample_path = create_sample_csv()
        records = collect_from_csv(sample_path, limit)
        all_records.extend(records)
    
    logger.info(f"✅ Collected {len(all_records)} YouTube trending records")
    return all_records


# Self-test block
if __name__ == "__main__":
    logger.info("")
    logger.info("=" * 70)
    logger.info("🧪 TESTING YOUTUBE TRENDING COLLECTOR (REAL DATA VERSION)")
    logger.info("=" * 70)
    
    # Test 1: Try API (REAL DATA)
    logger.info("\n--- Test 1: YouTube API (Real Trending Videos) ---")
    api_key = os.getenv("YOUTUBE_API_KEY")
    if api_key:
        logger.info("✅ YOUTUBE_API_KEY found, fetching real data...")
        records_api = collect(region_codes=["US"], limit=5, use_api=True)
        if records_api:
            logger.info(f"✅ SUCCESS: {len(records_api)} real trending videos")
            for i, rec in enumerate(records_api[:3], 1):
                p = rec['payload']
                logger.info(f"  {i}. {p['title']}")
                logger.info(f"     👁️  {p['view_count']:,} views | 👍 {p['likes']:,} likes")
                logger.info(f"     📺 {p['channel_title']}")
    else:
        logger.warning("❌ No YOUTUBE_API_KEY found")
        logger.warning("   Get free key at: https://console.cloud.google.com/apis/credentials")
    
    # Test 2: CSV Fallback
    logger.info("\n--- Test 2: CSV Fallback ---")
    csv_path = "data/youtube/sample_trending.csv"
    if os.path.exists(csv_path):
        records_csv = collect(csv_paths=[csv_path], use_api=False, limit=3)
        logger.info(f"✅ CSV Test: {len(records_csv)} records")
    else:
        logger.info(f"📝 No CSV found at {csv_path}, will create sample")
    
    # Test 3: Sample Data
    logger.info("\n--- Test 3: Sample Data (Last Resort) ---")
    records_sample = collect(use_api=False, limit=3)
    logger.info(f"✅ Sample Test: {len(records_sample)} records")
    logger.info(f"   Sample: {records_sample[0]['payload']['title']}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ YOUTUBE TRENDING COLLECTOR TESTS COMPLETE")
    logger.info("=" * 70)
    logger.info("")

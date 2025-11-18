"""
Wikipedia & Backlinko KOL Rankings Collector - PHASE 1B SCALE-UP VERSION
========================================================================

Collects top KOL/influencer rankings from Wikipedia and Backlinko HTML tables.

✨ NEW in Phase 1B: Multi-platform support for large-scale ingestion (400+ records).

Data sources:
- Wikipedia: List of most-followed accounts on social media platforms
  - YouTube: Top subscribed channels
  - Instagram: Top followed accounts  
  - TikTok: Top followed accounts
  - Twitter/X: Top followed accounts
- Backlinko: Top influencers by platform and niche

Phase 1B Features:
------------------
- Multi-platform scraping: 4 platforms simultaneously
- Large table parsing: 100+ rows per platform
- Robust error handling: Skip failed platforms, continue collection
- Rate limiting: Delay between requests to avoid IP blocking

Target: 400+ records (4 platforms × 100 rows each)

Output: Normalized records with kol_id, platform, source, payload, ingest_ts
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Wikipedia URLs for top accounts
WIKIPEDIA_URLS = {
    "instagram": "https://en.wikipedia.org/wiki/List_of_most-followed_Instagram_accounts",
    "youtube": "https://en.wikipedia.org/wiki/List_of_most-subscribed_YouTube_channels",
    "tiktok": "https://en.wikipedia.org/wiki/List_of_most-followed_TikTok_accounts",
    "twitter": "https://en.wikipedia.org/wiki/List_of_most-followed_Twitter_accounts",
}

# Sample Backlinko-style data (would be scraped in production)
BACKLINKO_SAMPLE_DATA = [
    {
        "rank": 1,
        "name": "MrBeast",
        "platform": "youtube",
        "followers": 200000000,
        "niche": "entertainment",
        "country": "USA"
    },
    {
        "rank": 2,
        "name": "PewDiePie",
        "platform": "youtube",
        "followers": 111000000,
        "niche": "gaming",
        "country": "Sweden"
    },
    {
        "rank": 3,
        "name": "Cristiano Ronaldo",
        "platform": "instagram",
        "followers": 600000000,
        "niche": "sports",
        "country": "Portugal"
    },
    {
        "rank": 4,
        "name": "Kylie Jenner",
        "platform": "instagram",
        "followers": 400000000,
        "niche": "lifestyle",
        "country": "USA"
    },
    {
        "rank": 5,
        "name": "Charli D'Amelio",
        "platform": "tiktok",
        "followers": 150000000,
        "niche": "dance",
        "country": "USA"
    }
]


def fetch_wikipedia_table(platform: str) -> Optional[pd.DataFrame]:
    """
    Fetches and parses Wikipedia table for most-followed accounts.
    
    Args:
        platform: Platform name (instagram, youtube, tiktok, twitter)
    
    Returns:
        DataFrame with columns: rank, account, owner, followers, etc.
        None if fetch fails
    """
    url = WIKIPEDIA_URLS.get(platform.lower())
    if not url:
        logger.warning(f"Unknown platform: {platform}")
        return None
    
    try:
        logger.info(f"Fetching Wikipedia data for {platform}: {url}")
        
        # Fetch page with proper User-Agent to avoid 403
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse tables
        tables = pd.read_html(response.text)
        
        if not tables:
            logger.warning(f"No tables found for {platform}")
            return None
        
        # Take first table (usually the main ranking)
        df = tables[0]
        logger.info(f"Found table with {len(df)} rows for {platform}")
        
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch Wikipedia data for {platform}: {e}")
        return None


def normalize_wikipedia_record(row: pd.Series, platform: str) -> Dict[str, Any]:
    """
    Normalizes a Wikipedia table row into canonical format.
    
    Args:
        row: DataFrame row
        platform: Platform name
    
    Returns:
        Normalized record dict
    """
    # Extract columns (Wikipedia tables vary, so we handle flexibly)
    kol_id = str(row.get("Account", row.get("Channel", row.get("Username", "unknown"))))
    
    # Clean kol_id (remove @ symbols, parentheses, etc.)
    kol_id = kol_id.replace("@", "").strip()
    if "(" in kol_id:
        kol_id = kol_id.split("(")[0].strip()
    
    # Build payload with all available columns
    payload = row.to_dict()
    
    # Add metadata
    payload["_source_platform"] = platform
    payload["_fetch_time"] = datetime.utcnow().isoformat()
    
    return {
        "kol_id": kol_id,
        "platform": platform,
        "source": "wikipedia_backlinko",
        "payload": payload,
        "ingest_ts": datetime.utcnow().isoformat()
    }


def collect_wikipedia(platforms: Optional[List[str]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Collects KOL rankings from Wikipedia for multiple platforms.
    
    ✨ PHASE 1B: Enhanced to fetch ALL platforms by default (400+ records).
    
    Args:
        platforms: List of platforms to fetch. 
                   Phase 1B default: ["youtube", "instagram", "tiktok", "twitter"] (all 4)
        limit: Max records per platform (Phase 1B default: 100+)
    
    Returns:
        List of normalized records
        
    Phase 1B Examples:
        # Fetch all 4 platforms, 100 rows each = 400 records
        >>> records = collect_wikipedia()
        
        # Fetch specific platforms
        >>> records = collect_wikipedia(platforms=["youtube", "instagram"])
        
        # Custom limit per platform
        >>> records = collect_wikipedia(limit=50)  # 4 platforms × 50 = 200 records
    """
    # Phase 1B: Default to ALL platforms for maximum data collection
    if platforms is None:
        platforms = list(WIKIPEDIA_URLS.keys())  # All 4 platforms
    
    logger.info(f"=" * 70)
    logger.info(f"🔵 PHASE 1B: LARGE-SCALE WIKIPEDIA COLLECTION")
    logger.info(f"=" * 70)
    logger.info(f"📋 Platforms: {', '.join(platforms)}")
    logger.info(f"📊 Limit per platform: {limit or 'No limit (fetch all)'}")
    logger.info(f"🎯 Estimated records: {len(platforms)} × 100+ rows")
    logger.info("")
    
    all_records = []
    successful_platforms = 0
    failed_platforms = []
    
    for platform in platforms:
        logger.info(f"🔍 Fetching: {platform.upper()}")
        
        # Fetch table
        df = fetch_wikipedia_table(platform)
        if df is None or df.empty:
            logger.warning(f"⚠️  Skipped {platform}: No data fetched")
            failed_platforms.append(platform)
            continue
        
        # Apply limit
        if limit:
            df = df.head(limit)
        
        # Normalize records
        for _, row in df.iterrows():
            try:
                record = normalize_wikipedia_record(row, platform)
                all_records.append(record)
            except Exception as e:
                logger.warning(f"   Skipped row for {platform}: {e}")
                continue
        
        successful_platforms += 1
        logger.info(f"✅ Collected {len(df)} records for {platform}")
        
        # Phase 1B: Rate limiting between platforms (avoid IP blocking)
        import time
        if platform != platforms[-1]:  # Don't delay after last platform
            time.sleep(1.5)
    
    logger.info("")
    logger.info(f"=" * 70)
    logger.info(f"📊 WIKIPEDIA COLLECTION SUMMARY")
    logger.info(f"=" * 70)
    logger.info(f"   Successful: {successful_platforms}/{len(platforms)} platforms")
    if failed_platforms:
        logger.info(f"   Failed: {', '.join(failed_platforms)}")
    logger.info(f"   Total records: {len(all_records)}")
    logger.info(f"=" * 70)
    logger.info("")
    
    return all_records


def collect_backlinko(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Collects KOL ranking data from Backlinko-style sources.
    
    In production, this would scrape actual Backlinko articles.
    For now, uses sample data.
    
    Args:
        limit: Max records to return
    
    Returns:
        List of normalized records
    """
    logger.info("Collecting Backlinko ranking data...")
    
    data = BACKLINKO_SAMPLE_DATA[:limit] if limit else BACKLINKO_SAMPLE_DATA
    
    records = []
    for item in data:
        record = {
            "kol_id": item["name"].replace(" ", "_").lower(),
            "platform": item["platform"],
            "source": "wikipedia_backlinko",
            "payload": {
                "name": item["name"],
                "rank": item["rank"],
                "followers": item["followers"],
                "niche": item["niche"],
                "country": item["country"],
                "_source": "backlinko_sample",
                "_fetch_time": datetime.utcnow().isoformat()
            },
            "ingest_ts": datetime.utcnow().isoformat()
        }
        records.append(record)
    
    logger.info(f"Collected {len(records)} Backlinko records")
    return records


def collect(limit: Optional[int] = None, source: str = "both", platforms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Main entry point for wikipedia_backlinko collector.
    
    ✨ PHASE 1B: Enhanced with multi-platform support.
    
    Args:
        limit: Max records per platform (Phase 1B: 100+ recommended)
        source: "wikipedia", "backlinko", or "both" (default)
        platforms: List of platforms for Wikipedia scraping
                   Phase 1B default: ["youtube", "instagram", "tiktok", "twitter"]
    
    Returns:
        List of normalized records
    
    Phase 1B Examples:
        # Collect 400+ records from all Wikipedia platforms
        >>> records = collect(limit=100, source="wikipedia")
        
        # Collect from all sources
        >>> records = collect(limit=50, source="both")
        
        # Specific platforms only
        >>> records = collect(platforms=["youtube", "instagram"], limit=100)
    """
    all_records = []
    
    if source in ("wikipedia", "both"):
        # Phase 1B: Collect from ALL platforms by default
        wiki_records = collect_wikipedia(platforms=platforms, limit=limit)
        all_records.extend(wiki_records)
    
    if source in ("backlinko", "both"):
        backlinko_records = collect_backlinko(limit=limit)
        all_records.extend(backlinko_records)
    
    logger.info(f"✅ Total collected: {len(all_records)} records")
    return all_records


if __name__ == "__main__":
    # Self-test
    print("=== Wikipedia & Backlinko Collector Test ===\n")
    
    # Test Backlinko collection (no network required)
    print("1. Testing Backlinko collection...")
    records = collect_backlinko(limit=3)
    print(f"   ✅ Collected {len(records)} Backlinko records")
    print(f"   Sample: {records[0]['kol_id']} - {records[0]['payload']['name']}\n")
    
    # Test Wikipedia collection (requires network)
    print("2. Testing Wikipedia collection (YouTube only)...")
    try:
        wiki_records = collect_wikipedia(platforms=["youtube"], limit=5)
        if wiki_records:
            print(f"   ✅ Collected {len(wiki_records)} Wikipedia records")
            print(f"   Sample: {wiki_records[0]['kol_id']}\n")
        else:
            print(f"   ⚠️ No Wikipedia records (check network/URL)\n")
    except Exception as e:
        print(f"   ⚠️ Wikipedia collection failed: {e}\n")
    
    # Test main collect function
    print("3. Testing main collect() with both sources...")
    all_records = collect(limit=5, source="both")
    print(f"   ✅ Total: {len(all_records)} records from both sources\n")
    
    print("✅ wikipedia_backlinko collector ready!")

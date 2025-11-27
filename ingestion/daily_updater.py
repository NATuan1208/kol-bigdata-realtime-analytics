"""
Daily YouTube Trending Data Updater
====================================
Tự động tải YouTube Trending data hàng ngày từ API.

Usage:
    python ingestion/daily_updater.py              # Chạy 1 lần
    
    # Hoặc schedule với cron (Linux/Mac):
    0 2 * * * cd /path/to/kol-platform && python ingestion/daily_updater.py
    
    # Hoặc Windows Task Scheduler:
    # Create task: Run python ingestion/daily_updater.py at 2:00 AM daily
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ingestion.sources import youtube_trending
from ingestion.minio_client import upload_jsonl_records

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_daily_update():
    """
    Chạy daily update: tải YouTube Trending từ API và upload to Bronze.
    """
    print("\n" + "=" * 70)
    print("📅 DAILY YOUTUBE TRENDING UPDATE")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Get API key
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        logger.warning("⚠️  YOUTUBE_API_KEY not found in environment")
        logger.warning("   Set it in .env.kol or export YOUTUBE_API_KEY=...")
        logger.warning("   Update skipped.")
        return False
    
    logger.info(f"✅ API Key found (first 10 chars): {api_key[:10]}...")
    
    # Collect today's YouTube trending
    logger.info("\n📺 Collecting YouTube Trending videos...")
    logger.info("   Regions: US, VN, KR, JP, BR, IN")
    logger.info("   Limit: 50 videos per region")
    
    try:
        records = youtube_trending.collect(
            api_key=api_key,
            region_codes=['US', 'VN', 'KR', 'JP', 'BR', 'IN'],
            limit=50,
            use_api=True
        )
        
        logger.info(f"✅ Collected {len(records)} trending videos")
        
        if not records:
            logger.warning("⚠️  No records collected")
            return False
        
        # Upload to Bronze
        logger.info(f"\n📤 Uploading to Bronze layer...")
        result = upload_jsonl_records('youtube_trending', records)
        
        if result:
            logger.info(f"✅ Successfully uploaded!")
            logger.info(f"   Path: {result['s3_path']}")
            logger.info(f"   Records: {result['records_count']}")
            logger.info(f"   Size: {result['file_size_bytes'] / 1024:.2f} KB")
            return True
        else:
            logger.error("❌ Upload failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during collection: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """Main entry point."""
    success = run_daily_update()
    
    print("\n" + "=" * 70)
    if success:
        logger.info("✅ DAILY UPDATE COMPLETED SUCCESSFULLY")
    else:
        logger.error("❌ DAILY UPDATE FAILED")
    print("=" * 70 + "\n")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

"""
Batch Ingestion CLI - KOL Analytics Platform
=============================================

Command-line interface for collecting data from multiple sources and uploading
to MinIO Bronze layer in JSONL format.

Usage:
------
# Phase 1B: Large-scale collection (multi-day, multi-region)
python ingestion/batch_ingest.py --source youtube_trending --days-back 7 --regions VN US KR JP --limit 50 --upload
python ingestion/batch_ingest.py --source all --days-back 30 --regions VN US KR JP BR --limit 50 --upload

# Collect from specific source (default: single region, today only)
python ingestion/batch_ingest.py --source youtube_trending --limit 20
python ingestion/batch_ingest.py --source wikipedia_backlinko --limit 100
python ingestion/batch_ingest.py --source instagram_influencer --limit 50000 --create-sample

# Collect and upload to MinIO
python ingestion/batch_ingest.py --source all --limit 50 --upload

# Show available sources
python ingestion/batch_ingest.py --list-sources
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# Fix Windows encoding for emoji support
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ingestion.sources import short_video_trends, youtube_trending, wikipedia_backlinko, instagram_influencer
from ingestion.minio_client import upload_jsonl_records
from ingestion.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Available data sources
AVAILABLE_SOURCES = {
    'youtube_trending': {
        'module': youtube_trending,
        'description': 'YouTube trending videos (Real-time API)',
        'default_limit': 50,
        'requires_api_key': True
    },
    'wikipedia_backlinko': {
        'module': wikipedia_backlinko,
        'description': 'Wikipedia KOL rankings (Web scraping)',
        'default_limit': 100,
        'requires_api_key': False
    },
    'short_video_trends': {
        'module': short_video_trends,
        'description': 'YouTube Shorts + TikTok global trends (HuggingFace) - PHASE 1B',
        'default_limit': 50000,
        'requires_api_key': False
    },
    'instagram_influencer': {
        'module': instagram_influencer,
        'description': 'Instagram influencer dataset (34k influencers, 10M posts sample) - PHASE 1B',
        'default_limit': 50000,
        'requires_api_key': False
    }
}


def list_sources():
    """Display all available data sources."""
    print("\n" + "=" * 70)
    print("📊 AVAILABLE DATA SOURCES")
    print("=" * 70)
    
    for source_name, source_info in AVAILABLE_SOURCES.items():
        api_key_required = "🔑 API key required" if source_info['requires_api_key'] else "✅ No setup needed"
        print(f"\n🔹 {source_name}")
        print(f"   {source_info['description']}")
        print(f"   Default limit: {source_info['default_limit']} records")
        print(f"   Setup: {api_key_required}")
    
    print("\n" + "=" * 70)
    print("\n💡 Usage examples:")
    print(f"   python ingestion/batch_ingest.py --source youtube_trending --limit 20")
    print(f"   python ingestion/batch_ingest.py --source all --limit 50 --upload")
    print("=" * 70 + "\n")


def collect_from_source(source_name: str, limit: int = None) -> List[Dict[str, Any]]:
    """
    Collect data from a specific source.
    
    Args:
        source_name: Name of the data source
        limit: Maximum number of records to collect
        
    Returns:
        List of normalized records
    """
    if source_name not in AVAILABLE_SOURCES:
        logger.error(f"Unknown source: {source_name}")
        logger.info(f"Available sources: {', '.join(AVAILABLE_SOURCES.keys())}")
        return []
    
    source_info = AVAILABLE_SOURCES[source_name]
    module = source_info['module']
    
    # Use default limit if not specified
    if limit is None:
        limit = source_info['default_limit']
    
    logger.info("=" * 70)
    logger.info(f"📥 COLLECTING FROM: {source_name}")
    logger.info("=" * 70)
    logger.info(f"Description: {source_info['description']}")
    logger.info(f"Limit: {limit} records")
    
    try:
        # Call the collect() function from the source module
        if source_name == 'youtube_trending':
            # Check for API key
            api_key = os.getenv('YOUTUBE_API_KEY')
            if not api_key:
                logger.warning("⚠️  YOUTUBE_API_KEY not found in environment")
                logger.warning("   Set it in .env.kol or export YOUTUBE_API_KEY=...")
                logger.warning("   Falling back to sample data")
            
            # PHASE 1B: Pass days_back and region_codes from CLI args
            days_back = getattr(module, '_cli_days_back', 0)  # Default: today only
            region_codes = getattr(module, '_cli_region_codes', ['US', 'VN'])  # Default: US, VN
            
            records = module.collect(
                region_codes=region_codes,
                days_back=days_back,
                limit=limit,
                use_api=True
            )
        
        elif source_name == 'wikipedia_backlinko':
            records = module.collect(
                source='wikipedia',
                limit=limit
            )
        
        elif source_name == 'short_video_trends':
            # PHASE 1B: YouTube Shorts + TikTok trends (HuggingFace)
            # Support HuggingFace datasets
            huggingface_dataset = getattr(module, '_cli_huggingface_dataset', None)
            
            records = module.collect(
                csv_paths=None,  # Auto-discover or create sample
                limit=limit,
                create_sample=True,  # Enable sample creation if no data found
                huggingface_dataset=huggingface_dataset  # HuggingFace support
            )
        
        elif source_name == 'instagram_influencer':
            # PHASE 1B: Instagram influencer dataset (sample ~500MB-1GB)
            sample_dir = getattr(module, '_cli_sample_dir', None)
            create_sample = getattr(module, '_cli_create_sample', False)
            
            records = module.collect(
                sample_dir=sample_dir,
                limit=limit,
                create_sample=create_sample
            )
        
        else:
            logger.error(f"No collection logic for source: {source_name}")
            return []
        
        logger.info(f"✅ Successfully collected {len(records)} records from {source_name}")
        return records
        
    except Exception as e:
        logger.error(f"❌ Failed to collect from {source_name}: {e}")
        return []


def collect_all_sources(limit_per_source: int = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect data from all available sources.
    
    Args:
        limit_per_source: Maximum records per source (uses defaults if None)
        
    Returns:
        Dictionary mapping source name to list of records
    """
    results = {}
    
    logger.info("\n" + "=" * 70)
    logger.info("🚀 COLLECTING FROM ALL SOURCES")
    logger.info("=" * 70)
    
    for source_name in AVAILABLE_SOURCES.keys():
        records = collect_from_source(source_name, limit_per_source)
        results[source_name] = records
        
        # Brief pause between sources
        import time
        time.sleep(1)
    
    # Summary
    total_records = sum(len(records) for records in results.values())
    logger.info("\n" + "=" * 70)
    logger.info("📊 COLLECTION SUMMARY")
    logger.info("=" * 70)
    for source_name, records in results.items():
        logger.info(f"   {source_name}: {len(records)} records")
    logger.info(f"\n   TOTAL: {total_records} records")
    logger.info("=" * 70 + "\n")
    
    return results


def upload_to_bronze(source_name: str, records: List[Dict[str, Any]]) -> bool:
    """
    Upload collected records to MinIO Bronze layer.
    
    Args:
        source_name: Name of the data source
        records: List of records to upload
        
    Returns:
        True if upload successful, False otherwise
    """
    if not records:
        logger.warning(f"⚠️  No records to upload for {source_name}")
        return False
    
    try:
        logger.info(f"📤 Uploading {len(records)} records from {source_name} to MinIO Bronze...")
        
        result = upload_jsonl_records(source_name, records)
        
        if result:
            logger.info(f"✅ Successfully uploaded {source_name}")
            logger.info(f"   Path: {result['s3_path']}")
            logger.info(f"   Records: {result['records_count']}")
            logger.info(f"   Size: {result['file_size_bytes']} bytes")
            return True
        else:
            logger.error(f"❌ Failed to upload {source_name}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Upload error for {source_name}: {e}")
        return False


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Batch data ingestion for KOL Analytics Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available sources
  %(prog)s --list-sources
  
  # Collect from YouTube (requires API key)
  %(prog)s --source youtube_trending --limit 20
  
  # Collect from Wikipedia (no API key needed)
  %(prog)s --source wikipedia_backlinko --limit 100
  
  # Collect from all sources and upload to MinIO
  %(prog)s --source all --limit 50 --upload
  
Environment Variables:
  YOUTUBE_API_KEY    YouTube Data API v3 key (for youtube_trending)
  
Configuration:
  See .env.kol for MinIO and other settings
        """
    )
    
    parser.add_argument(
        '--source',
        type=str,
        choices=list(AVAILABLE_SOURCES.keys()) + ['all'],
        help='Data source to collect from (or "all" for all sources)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of records to collect per source'
    )
    
    parser.add_argument(
        '--upload',
        action='store_true',
        help='Upload collected data to MinIO Bronze layer'
    )
    
    parser.add_argument(
        '--list-sources',
        action='store_true',
        help='List all available data sources and exit'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Collect data but do not upload (even if --upload specified)'
    )
    
    # PHASE 1B: Multi-day and multi-region parameters
    parser.add_argument(
        '--days-back',
        type=int,
        default=0,
        help='Number of days to fetch (Phase 1B): 0=today only, 7=past week, 30=past month (default: 0)'
    )
    
    parser.add_argument(
        '--regions',
        type=str,
        nargs='+',
        default=['US', 'VN'],
        help='List of region codes for YouTube trending (Phase 1B): VN US KR JP BR IN etc. (default: US VN)'
    )
    
    parser.add_argument(
        '--huggingface',
        type=str,
        help='HuggingFace dataset name for short_video_trends (Phase 1B): e.g., TarekMasryo/YouTube-Shorts-TikTok-Trends-2025'
    )
    
    parser.add_argument(
        '--sample-dir',
        type=str,
        help='Local sample directory for instagram_influencer (Phase 1B): e.g., data/instagram/'
    )
    
    parser.add_argument(
        '--create-sample',
        action='store_true',
        help='Create sample data for instagram_influencer testing (Phase 1B)'
    )
    
    args = parser.parse_args()
    
    # Handle --list-sources
    if args.list_sources:
        list_sources()
        return 0
    
    # Validate arguments
    if not args.source:
        parser.print_help()
        logger.error("\n❌ Error: --source is required")
        return 1
    
    # Print configuration
    config = Config()
    logger.info("\n" + "=" * 70)
    logger.info("⚙️  CONFIGURATION")
    logger.info("=" * 70)
    logger.info(f"MinIO Endpoint: {config.MINIO_ENDPOINT}")
    logger.info(f"MinIO Bucket: {config.MINIO_BUCKET}")
    logger.info(f"Upload enabled: {args.upload and not args.dry_run}")
    logger.info(f"Dry run: {args.dry_run}")
    # PHASE 1B configuration
    logger.info(f"Days back: {args.days_back} days (0=today, 7=week, 30=month)")
    logger.info(f"Regions: {', '.join(args.regions)}")
    if args.huggingface:
        logger.info(f"HuggingFace dataset: {args.huggingface}")
    logger.info("=" * 70 + "\n")
    
    # Store Phase 1B parameters in modules for collect_from_source()
    youtube_trending._cli_days_back = args.days_back
    youtube_trending._cli_region_codes = args.regions
    short_video_trends._cli_huggingface_dataset = args.huggingface  # NEW: HuggingFace support
    instagram_influencer._cli_sample_dir = args.sample_dir  # NEW: Instagram sample directory
    instagram_influencer._cli_create_sample = args.create_sample  # NEW: Instagram sample creation
    
    # Collect data
    start_time = datetime.now()
    
    if args.source == 'all':
        # Collect from all sources
        all_results = collect_all_sources(args.limit)
        
        # Upload if requested
        if args.upload and not args.dry_run:
            logger.info("\n📤 UPLOADING TO MINIO BRONZE LAYER")
            logger.info("=" * 70)
            
            upload_success = {}
            for source_name, records in all_results.items():
                success = upload_to_bronze(source_name, records)
                upload_success[source_name] = success
            
            # Upload summary
            logger.info("\n" + "=" * 70)
            logger.info("📊 UPLOAD SUMMARY")
            logger.info("=" * 70)
            for source_name, success in upload_success.items():
                status = "✅ Success" if success else "❌ Failed"
                logger.info(f"   {source_name}: {status}")
            logger.info("=" * 70)
    
    else:
        # Collect from single source
        records = collect_from_source(args.source, args.limit)
        
        # Upload if requested
        if args.upload and not args.dry_run:
            upload_to_bronze(args.source, records)
        elif args.dry_run:
            logger.info(f"\n🔍 DRY RUN: Would upload {len(records)} records (skipped)")
    
    # Execution time
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"\n⏱️  Total execution time: {elapsed:.2f} seconds")
    
    logger.info("\n✅ Batch ingestion complete!\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())

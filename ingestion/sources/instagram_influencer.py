"""
Instagram Influencer Dataset Collector
Dataset: ksb2043/instagram_influencer_dataset (GitHub)
Source: https://sites.google.com/site/sbkimcv/dataset/instagram-influencer-dataset

Dataset info:
- 33,935 Instagram influencers (9 categories)
- 10,180,500 posts (300 posts per influencer)
- Metadata: caption, usertags, hashtags, timestamp, sponsorship, likes, comments
- Categories: Beauty, Family, Fashion, Fitness, Food, Interior, Pet, Travel, Other
- Published: WWW'20 (The Web Conference 2020)

Phase 1B: Sample ~50k posts (~500MB-1GB) for Bronze layer
"""

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Dataset configuration
DATASET_BASE_URL = "https://sites.google.com/site/sbkimcv/dataset/instagram-influencer-dataset"
CATEGORIES = ["Beauty", "Family", "Fashion", "Fitness", "Food", "Interior", "Pet", "Travel", "Other"]

# Sample configuration for Phase 1B
DEFAULT_SAMPLE_SIZE = 50000  # Target ~500MB-1GB
POSTS_PER_INFLUENCER = 300


def normalize_instagram_record(post_data: Dict, influencer_id: str, category: str) -> Dict:
    """
    Normalize Instagram post metadata to canonical format.
    
    Expected post_data fields:
    - likes (int)
    - comments (int or list)
    - caption (str)
    - timestamp (str/int)
    - hashtags (list)
    - usertags (list)
    - sponsorship (bool)
    """
    try:
        # Extract engagement metrics
        likes = post_data.get('likes', 0) or 0
        
        # Comments can be int or list
        comments_data = post_data.get('comments', 0)
        if isinstance(comments_data, list):
            comment_count = len(comments_data)
        else:
            comment_count = comments_data or 0
        
        # Extract content features
        caption = post_data.get('caption', '') or ''
        hashtags = post_data.get('hashtags', []) or []
        usertags = post_data.get('usertags', []) or []
        is_sponsored = post_data.get('sponsorship', False) or False
        
        # Parse timestamp
        timestamp = post_data.get('timestamp', '')
        try:
            if isinstance(timestamp, int):
                post_time = datetime.fromtimestamp(timestamp)
            else:
                post_time = datetime.fromisoformat(str(timestamp))
        except:
            post_time = datetime.now()
        
        # Build canonical payload
        payload = {
            'influencer_id': influencer_id,
            'category': category,
            'likes': likes,
            'comments': comment_count,
            'engagement': likes + comment_count,
            'caption': caption[:500] if caption else '',  # Truncate long captions
            'caption_length': len(caption),
            'hashtag_count': len(hashtags),
            'hashtags': hashtags[:20] if hashtags else [],  # Limit hashtags
            'usertag_count': len(usertags),
            'usertags': usertags[:10] if usertags else [],  # Limit usertags
            'is_sponsored': is_sponsored,
            'post_timestamp': post_time.isoformat(),
            'post_date': post_time.strftime('%Y-%m-%d'),
            'post_hour': post_time.hour,
            'post_day_of_week': post_time.strftime('%A'),
        }
        
        # Return canonical format
        return {
            'kol_id': influencer_id,
            'platform': 'instagram',
            'source': 'instagram_influencer',
            'payload': payload,
            'ingest_ts': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error normalizing Instagram record: {e}")
        # Return minimal record on error
        return {
            'kol_id': influencer_id or 'unknown',
            'platform': 'instagram',
            'source': 'instagram_influencer',
            'payload': {
                'error': str(e),
                'raw_data': str(post_data)[:200]
            },
            'ingest_ts': datetime.now().isoformat()
        }


def load_from_local_sample(sample_dir: Path, limit: Optional[int] = None) -> List[Dict]:
    """
    Load Instagram metadata from local downloaded sample.
    
    Expected structure:
    sample_dir/
        metadata/
            influencer_1/
                post_1.json
                post_2.json
                ...
            influencer_2/
                ...
        influencer_categories.json  # Mapping: {influencer_id: category}
    """
    records = []
    
    if not sample_dir.exists():
        logger.error(f"Sample directory not found: {sample_dir}")
        return records
    
    # Load category mapping
    category_file = sample_dir / 'influencer_categories.json'
    category_map = {}
    if category_file.exists():
        try:
            with open(category_file, 'r', encoding='utf-8') as f:
                category_map = json.load(f)
            logger.info(f"✅ Loaded category mapping for {len(category_map)} influencers")
        except Exception as e:
            logger.warning(f"Failed to load category mapping: {e}")
    
    # Load metadata files
    metadata_dir = sample_dir / 'metadata'
    if not metadata_dir.exists():
        logger.error(f"Metadata directory not found: {metadata_dir}")
        return records
    
    influencer_dirs = list(metadata_dir.iterdir())
    random.shuffle(influencer_dirs)  # Random sampling
    
    logger.info(f"📂 Found {len(influencer_dirs)} influencer directories")
    
    for influencer_dir in influencer_dirs:
        if not influencer_dir.is_dir():
            continue
        
        influencer_id = influencer_dir.name
        category = category_map.get(influencer_id, 'Other')
        
        # Load posts for this influencer
        post_files = list(influencer_dir.glob('*.json'))
        
        for post_file in post_files:
            try:
                with open(post_file, 'r', encoding='utf-8') as f:
                    post_data = json.load(f)
                
                record = normalize_instagram_record(post_data, influencer_id, category)
                records.append(record)
                
                if limit and len(records) >= limit:
                    logger.info(f"✅ Reached limit of {limit} records")
                    return records
                    
            except Exception as e:
                logger.debug(f"Failed to load {post_file}: {e}")
                continue
        
        if len(records) % 10000 == 0 and len(records) > 0:
            logger.info(f"📊 Loaded {len(records):,} posts so far...")
    
    logger.info(f"✅ Total loaded: {len(records):,} posts from {len(influencer_dirs)} influencers")
    return records


def create_sample_data(count: int = 1000) -> List[Dict]:
    """
    Create sample Instagram influencer records for testing.
    """
    records = []
    
    influencer_ids = [f"influencer_{i}" for i in range(1, 101)]
    
    for i in range(count):
        influencer_id = random.choice(influencer_ids)
        category = random.choice(CATEGORIES)
        
        # Simulate realistic engagement
        likes = random.randint(100, 100000)
        comments = random.randint(10, 5000)
        is_sponsored = random.random() < 0.15  # ~15% sponsored posts
        
        post_data = {
            'likes': likes,
            'comments': comments,
            'caption': f"Sample Instagram post #{i} from {influencer_id}",
            'hashtags': [f"#tag{j}" for j in range(random.randint(3, 10))],
            'usertags': [f"@user{j}" for j in range(random.randint(0, 3))],
            'sponsorship': is_sponsored,
            'timestamp': datetime.now().isoformat()
        }
        
        record = normalize_instagram_record(post_data, influencer_id, category)
        records.append(record)
    
    return records


def collect(
    sample_dir: Optional[str] = None,
    limit: Optional[int] = None,
    create_sample: bool = False
) -> List[Dict]:
    """
    Collect Instagram influencer data.
    
    Args:
        sample_dir: Path to local sample directory (if already downloaded)
        limit: Maximum number of posts to collect
        create_sample: If True, generate sample data for testing
    
    Returns:
        List of normalized records
    """
    if create_sample:
        logger.info("🔧 Creating sample Instagram influencer data...")
        sample_size = limit if limit else 1000
        return create_sample_data(sample_size)
    
    if sample_dir:
        sample_path = Path(sample_dir)
        logger.info(f"📥 Loading Instagram data from local sample: {sample_path}")
        return load_from_local_sample(sample_path, limit=limit)
    
    # If no local sample, create sample data as fallback
    logger.warning("⚠️  No sample directory provided. Download instructions:")
    logger.warning("   1. Visit: https://sites.google.com/site/sbkimcv/dataset/instagram-influencer-dataset")
    logger.warning("   2. Download metadata sample (~1GB)")
    logger.warning("   3. Extract to data/instagram/")
    logger.warning("   4. Run: --source instagram_influencer --sample-dir data/instagram/")
    logger.warning("")
    logger.warning("   For now, creating sample data for testing...")
    
    return create_sample_data(limit if limit else 1000)


if __name__ == '__main__':
    # Test the collector
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("Instagram Influencer Dataset Collector - Test")
    print("=" * 60)
    
    # Test with sample data
    print("\n📊 Creating sample data...")
    records = collect(create_sample=True, limit=100)
    
    print(f"\n✅ Collected {len(records)} records")
    print(f"\n📋 Sample record:")
    print(json.dumps(records[0], indent=2, ensure_ascii=False))
    
    # Category distribution
    categories = {}
    sponsored_count = 0
    total_engagement = 0
    
    for record in records:
        payload = record['payload']
        cat = payload['category']
        categories[cat] = categories.get(cat, 0) + 1
        
        if payload.get('is_sponsored'):
            sponsored_count += 1
        
        total_engagement += payload.get('engagement', 0)
    
    print(f"\n📊 Statistics:")
    print(f"   Total records: {len(records)}")
    print(f"   Sponsored posts: {sponsored_count} ({sponsored_count/len(records)*100:.1f}%)")
    print(f"   Avg engagement: {total_engagement/len(records):.0f}")
    print(f"\n   Category distribution:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"      {cat}: {count} ({count/len(records)*100:.1f}%)")

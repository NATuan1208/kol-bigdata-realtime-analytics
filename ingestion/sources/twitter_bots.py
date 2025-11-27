"""
Twitter Human vs Bot Dataset Collector
=======================================

Thu thập dataset Twitter Human-Bots từ HuggingFace để train Trust Score model.

Dataset: airt-ml/twitter-human-bots
- 37,400 records
- Labels: "human" vs "bot"
- Features: followers, friends, verified, account_age, tweet patterns

Tại sao dataset này quan trọng?
- Đây là dữ liệu THẬT với labels đã được verify
- Có thể dùng trực tiếp để train XGBoost Trust Score model
- Bổ sung trust signals mà các dataset khác thiếu

Usage:
    python -m ingestion.sources.twitter_bots
    
    # Hoặc với limit
    python -m ingestion.sources.twitter_bots --limit 10000

Author: KOL Analytics Team (IE212 - UIT)
Date: 2025-11-26
"""

import json
import logging
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

DATASET_NAME = "airt-ml/twitter-human-bots"
SOURCE_NAME = "twitter_human_bots"
PLATFORM = "twitter"


def collect(
    limit: Optional[int] = None,
    upload_to_minio: bool = True
) -> Dict[str, Any]:
    """
    Thu thập Twitter Human-Bots dataset từ HuggingFace.
    
    Args:
        limit: Giới hạn số records (None = toàn bộ)
        upload_to_minio: Có upload lên MinIO không
        
    Returns:
        Dict với thông tin kết quả
        
    Example:
        >>> result = collect(limit=1000)
        >>> print(f"Collected {result['records_count']} records")
    """
    from datasets import load_dataset
    
    logger.info(f"📥 Loading dataset: {DATASET_NAME}")
    
    try:
        # Load dataset từ HuggingFace
        dataset = load_dataset(DATASET_NAME)
        
        # Dataset có thể có nhiều splits
        if 'train' in dataset:
            data = dataset['train']
        else:
            # Nếu không có train split, lấy split đầu tiên
            data = dataset[list(dataset.keys())[0]]
        
        total_records = len(data)
        logger.info(f"✅ Loaded {total_records} records from HuggingFace")
        
        # Giới hạn nếu cần
        if limit and limit < total_records:
            # Lấy mẫu balanced giữa human và bot
            data = data.shuffle(seed=42).select(range(limit))
            logger.info(f"📊 Limited to {limit} records")
        
        # Chuyển đổi sang canonical format
        records = []
        human_count = 0
        bot_count = 0
        
        for idx, row in enumerate(data):
            try:
                # Xác định account type
                account_type = row.get('account_type', 'unknown')
                if account_type == 'human':
                    human_count += 1
                elif account_type == 'bot':
                    bot_count += 1
                
                # Tạo kol_id từ user_id hoặc index
                kol_id = str(row.get('id', row.get('user_id', f'twitter_user_{idx}')))
                
                # Extract profile features
                profile = {
                    'user_id': kol_id,
                    'screen_name': row.get('screen_name', ''),
                    'name': row.get('name', ''),
                    'description': row.get('description', ''),
                    'followers_count': row.get('followers_count', 0),
                    'friends_count': row.get('friends_count', 0),  # following
                    'statuses_count': row.get('statuses_count', 0),  # tweets
                    'favourites_count': row.get('favourites_count', 0),  # likes
                    'verified': row.get('verified', False),
                    'default_profile': row.get('default_profile', False),
                    'default_profile_image': row.get('default_profile_image', False),
                    'has_url': bool(row.get('url', '')),
                    'created_at': row.get('created_at', ''),
                    'location': row.get('location', ''),
                    'lang': row.get('lang', 'en'),
                }
                
                # Tính derived features
                followers = profile['followers_count'] or 0
                friends = profile['friends_count'] or 0
                statuses = profile['statuses_count'] or 0
                
                derived_features = {
                    'followers_friends_ratio': followers / friends if friends > 0 else 0,
                    'friends_followers_ratio': friends / followers if followers > 0 else 0,
                    'tweets_per_follower': statuses / followers if followers > 0 else 0,
                    'has_description': bool(profile['description']),
                    'description_length': len(profile['description'] or ''),
                }
                
                # Trust label (ground truth)
                trust_label = {
                    'account_type': account_type,
                    'is_bot': 1 if account_type == 'bot' else 0,
                    'is_human': 1 if account_type == 'human' else 0,
                    'label_source': 'airt-ml/twitter-human-bots'
                }
                
                # Canonical format
                record = {
                    'kol_id': kol_id,
                    'platform': PLATFORM,
                    'source': SOURCE_NAME,
                    'payload': {
                        'profile': profile,
                        'derived_features': derived_features,
                        'trust_label': trust_label,
                    },
                    'ingest_ts': datetime.now(timezone.utc).isoformat()
                }
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Skipping row {idx}: {e}")
                continue
        
        logger.info(f"✅ Processed {len(records)} records")
        logger.info(f"   Human: {human_count} ({human_count/len(records)*100:.1f}%)")
        logger.info(f"   Bot: {bot_count} ({bot_count/len(records)*100:.1f}%)")
        
        # Upload to MinIO
        if upload_to_minio and records:
            try:
                from ingestion.minio_client import upload_jsonl_records
                result = upload_jsonl_records(SOURCE_NAME, records)
                logger.info(f"📤 Uploaded to MinIO: {result}")
            except Exception as e:
                logger.error(f"❌ Failed to upload to MinIO: {e}")
                # Save locally as backup
                save_locally(records)
        elif records:
            save_locally(records)
        
        return {
            'source': SOURCE_NAME,
            'records_count': len(records),
            'human_count': human_count,
            'bot_count': bot_count,
            'balance': f"{human_count}:{bot_count}",
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to load dataset: {e}")
        return {
            'source': SOURCE_NAME,
            'records_count': 0,
            'status': 'error',
            'error': str(e)
        }


def save_locally(records: List[Dict[str, Any]]):
    """Save records to local file."""
    import os
    
    output_dir = "data/twitter_bots"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"{output_dir}/twitter_human_bots_{timestamp}.jsonl"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    logger.info(f"💾 Saved {len(records)} records to {output_file}")


def get_sample_schema() -> Dict[str, Any]:
    """Trả về sample schema để documentation."""
    return {
        'kol_id': 'twitter_user_123',
        'platform': 'twitter',
        'source': 'twitter_human_bots',
        'payload': {
            'profile': {
                'user_id': '123456789',
                'screen_name': 'example_user',
                'followers_count': 1000,
                'friends_count': 500,
                'statuses_count': 2000,
                'verified': False,
                'created_at': '2020-01-01'
            },
            'derived_features': {
                'followers_friends_ratio': 2.0,
                'has_description': True,
                'description_length': 100
            },
            'trust_label': {
                'account_type': 'human',
                'is_bot': 0,
                'is_human': 1,
                'label_source': 'airt-ml/twitter-human-bots'
            }
        },
        'ingest_ts': '2025-11-26T12:00:00+00:00'
    }


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Collect Twitter Human-Bots dataset from HuggingFace'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of records (default: all ~37K)'
    )
    
    parser.add_argument(
        '--no-upload',
        action='store_true',
        help='Do not upload to MinIO, save locally only'
    )
    
    parser.add_argument(
        '--schema',
        action='store_true',
        help='Print sample schema and exit'
    )
    
    args = parser.parse_args()
    
    if args.schema:
        import json
        print(json.dumps(get_sample_schema(), indent=2))
        return
    
    print("\n" + "=" * 70)
    print("🤖 TWITTER HUMAN-BOTS DATASET COLLECTOR")
    print("=" * 70)
    print(f"   Dataset: {DATASET_NAME}")
    print(f"   Limit: {args.limit or 'All (~37K)'}")
    print(f"   Upload to MinIO: {not args.no_upload}")
    print("=" * 70 + "\n")
    
    result = collect(
        limit=args.limit,
        upload_to_minio=not args.no_upload
    )
    
    print("\n" + "=" * 70)
    print("📊 RESULT")
    print("=" * 70)
    for key, value in result.items():
        print(f"   {key}: {value}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

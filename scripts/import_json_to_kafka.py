#!/usr/bin/env python3
"""
Import JSON data files to Kafka topics
======================================

Imports existing JSON data files from data/tiktok_crawl/ into Kafka topics
for Hot Path testing.

Usage:
    python scripts/import_json_to_kafka.py --all
    python scripts/import_json_to_kafka.py --topic videos
    python scripts/import_json_to_kafka.py --topic profiles --limit 100
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("⚠️ kafka-python not installed. Install with: pip install kafka-python")


# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")

# Mapping: file pattern → Kafka topic
FILE_TOPIC_MAP = {
    "kol_videos_raw": "kol.videos.raw",
    "kol_profiles_raw": "kol.profiles.raw",
    "kol_products_raw": "kol.products.raw",
    "kol_comments_raw": "kol.comments.raw",
    "kol_discovery_raw": "kol.discovery.raw",
}

DATA_DIR = PROJECT_ROOT / "data" / "tiktok_crawl"


def load_json_file(filepath: Path) -> list:
    """Load JSON file and extract data records."""
    print(f"📂 Loading: {filepath.name}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    # Handle different formats
    if isinstance(raw_data, list):
        # Format: [{offset, timestamp, data: {...}}, ...]
        if raw_data and "data" in raw_data[0]:
            records = [item["data"] for item in raw_data if "data" in item]
        else:
            # Format: [{...}, {...}]
            records = raw_data
    elif isinstance(raw_data, dict):
        # Single record
        records = [raw_data]
    else:
        records = []
    
    print(f"   Found {len(records)} records")
    return records


def create_producer(kafka_servers: str = None):
    """Create Kafka producer."""
    if not KAFKA_AVAILABLE:
        return None
    
    servers = kafka_servers or KAFKA_BOOTSTRAP_SERVERS
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retries=3,
        )
        print(f"✅ Connected to Kafka: {servers}")
        return producer
    except Exception as e:
        print(f"❌ Failed to connect to Kafka: {e}")
        return None


def import_to_kafka(producer, topic: str, records: list, limit: int = None):
    """Import records to Kafka topic."""
    if limit:
        records = records[:limit]
    
    print(f"📤 Importing {len(records)} records to topic: {topic}")
    
    success = 0
    errors = 0
    
    for i, record in enumerate(records):
        try:
            # Use username or event_id as key for partitioning
            key = record.get("username") or record.get("event_id") or str(i)
            
            # Add import timestamp
            record["_imported_at"] = datetime.utcnow().isoformat()
            
            producer.send(topic, key=key, value=record)
            success += 1
            
            # Progress indicator
            if (i + 1) % 50 == 0:
                print(f"   Sent {i + 1}/{len(records)}...")
                
        except Exception as e:
            errors += 1
            print(f"   ❌ Error sending record {i}: {e}")
    
    # Flush to ensure all messages are sent
    producer.flush()
    
    print(f"✅ Imported: {success} success, {errors} errors")
    return success, errors


def find_data_files():
    """Find all JSON data files."""
    files = {}
    
    if not DATA_DIR.exists():
        print(f"❌ Data directory not found: {DATA_DIR}")
        return files
    
    for filepath in DATA_DIR.glob("*.json"):
        for pattern, topic in FILE_TOPIC_MAP.items():
            if pattern in filepath.name:
                files[topic] = filepath
                break
    
    return files


def main():
    parser = argparse.ArgumentParser(description="Import JSON to Kafka")
    parser.add_argument("--all", action="store_true", help="Import all data files")
    parser.add_argument("--topic", type=str, help="Import specific topic (videos/profiles/products/comments/discovery)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records per topic")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without sending")
    parser.add_argument("--kafka", type=str, default=KAFKA_BOOTSTRAP_SERVERS, help="Kafka bootstrap servers")
    
    args = parser.parse_args()
    
    # Override Kafka servers if specified
    kafka_servers = args.kafka
    
    print("=" * 60)
    print("  JSON to Kafka Importer")
    print("=" * 60)
    print(f"  Kafka: {kafka_servers}")
    print(f"  Data dir: {DATA_DIR}")
    print()
    
    # Find data files
    files = find_data_files()
    
    if not files:
        print("❌ No data files found!")
        return 1
    
    print("📁 Found data files:")
    for topic, filepath in files.items():
        print(f"   {topic} → {filepath.name}")
    print()
    
    # Filter by topic if specified
    if args.topic:
        topic_key = f"kol.{args.topic}.raw"
        if topic_key not in files:
            print(f"❌ Topic not found: {args.topic}")
            print(f"   Available: {', '.join(t.split('.')[1] for t in files.keys())}")
            return 1
        files = {topic_key: files[topic_key]}
    
    if not args.all and not args.topic:
        print("⚠️ Specify --all to import all files or --topic <name> for specific topic")
        return 1
    
    # Dry run mode
    if args.dry_run:
        print("🔍 DRY RUN - No data will be sent")
        for topic, filepath in files.items():
            records = load_json_file(filepath)
            count = len(records[:args.limit]) if args.limit else len(records)
            print(f"   Would import {count} records to {topic}")
        return 0
    
    # Create producer
    producer = create_producer(kafka_servers)
    if not producer:
        print("❌ Cannot create Kafka producer. Exiting.")
        return 1
    
    # Import each file
    total_success = 0
    total_errors = 0
    
    for topic, filepath in files.items():
        print()
        records = load_json_file(filepath)
        success, errors = import_to_kafka(producer, topic, records, args.limit)
        total_success += success
        total_errors += errors
    
    # Close producer
    producer.close()
    
    # Summary
    print()
    print("=" * 60)
    print("  IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Total success: {total_success}")
    print(f"  Total errors:  {total_errors}")
    print()
    
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

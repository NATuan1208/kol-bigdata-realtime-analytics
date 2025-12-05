#!/usr/bin/env python3
"""Import Kafka Export JSON files to Redpanda topics."""

import json
import os
import sys
from pathlib import Path

try:
    from kafka import KafkaProducer
except ImportError:
    print("ERROR: kafka-python not installed. Run: pip install kafka-python")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:19092")
EXPORT_DIR = PROJECT_ROOT / "data" / "kafka_export"

FILE_TOPIC_MAP = {
    "kol_discovery_raw": "kol.discovery.raw",
    "kol_profiles_raw": "kol.profiles.raw",
    "kol_videos_raw": "kol.videos.raw",
    "kol_comments_raw": "kol.comments.raw",
    "kol_products_raw": "kol.products.raw",
}

def main():
    print("="*60)
    print("  KAFKA EXPORT IMPORTER")
    print("="*60)
    
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BROKER],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    
    total = 0
    for json_file in EXPORT_DIR.glob("*.json"):
        name_parts = json_file.stem.rsplit("_", 2)
        base_name = "_".join(name_parts[:-2]) if len(name_parts) >= 3 else json_file.stem
        
        if base_name not in FILE_TOPIC_MAP:
            continue
            
        topic = FILE_TOPIC_MAP[base_name]
        print(f"\nImporting {json_file.name} -> {topic}")
        
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for i, record in enumerate(data):
            msg = record.get("data", record) if isinstance(record, dict) else record
            key = msg.get("event_id") or msg.get("username") or str(i)
            producer.send(topic, key=key, value=msg)
            total += 1
            if (i+1) % 200 == 0:
                print(f"  Sent {i+1}/{len(data)}...")
        
        print(f"  Done: {len(data)} messages")
    
    producer.flush()
    producer.close()
    print(f"\nTotal: {total} messages sent")

if __name__ == "__main__":
    main()

"""
Metrics Refresh - Re-push tracked KOLs để VideoStatsWorker scrape lại

Đọc danh sách KOL đang track từ Redis → Push lên kol.discovery.raw
→ VideoStatsWorker tự động scrape lại → Có velocity cho trending!

Chạy định kỳ mỗi 10-15 phút (cron hoặc loop):
    python -m ingestion.sources.metrics_refresh
    python -m ingestion.sources.metrics_refresh --interval 600  # loop mỗi 10 phút
"""

import argparse
import json
import time
import uuid
from datetime import datetime, timezone

import redis
from kafka import KafkaProducer

# Config
REDIS_HOST = "localhost"  # hoặc "kol-redis" nếu chạy trong Docker
REDIS_PORT = 16379  # Port expose ra localhost (6379 trong Docker)
REDIS_DB = 0

KAFKA_BROKER = "localhost:19092"  # hoặc "redpanda:9092" trong Docker
DISCOVERY_TOPIC = "kol.discovery.raw"


def get_tracked_kols(r: redis.Redis) -> list:
    """Lấy danh sách KOL đang được track từ Redis"""
    keys = r.keys("streaming_scores:*")
    usernames = []
    for key in keys:
        # key = "streaming_scores:username"
        username = key.replace("streaming_scores:", "")
        if username:
            usernames.append(username)
    return usernames


def push_to_discovery(producer: KafkaProducer, usernames: list):
    """Push usernames lên kol.discovery.raw để VideoStatsWorker scrape lại"""
    count = 0
    for username in usernames:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "refresh",  # Đánh dấu là refresh, không phải discovery mới
            "platform": "tiktok",
            "username": username,
            "source": "metrics_refresh",
        }
        
        producer.send(
            DISCOVERY_TOPIC,
            key=username.encode("utf-8"),
            value=json.dumps(event).encode("utf-8"),
        )
        count += 1
    
    producer.flush()
    return count


def main():
    parser = argparse.ArgumentParser(description="Re-push tracked KOLs for metrics refresh")
    parser.add_argument("--interval", type=int, default=0, 
                        help="Loop interval in seconds (0 = run once)")
    parser.add_argument("--redis-host", default=REDIS_HOST)
    parser.add_argument("--redis-port", type=int, default=REDIS_PORT)
    parser.add_argument("--kafka-broker", default=KAFKA_BROKER)
    args = parser.parse_args()
    
    # Connect Redis
    r = redis.Redis(host=args.redis_host, port=args.redis_port, db=REDIS_DB, decode_responses=True)
    
    # Connect Kafka
    producer = KafkaProducer(bootstrap_servers=args.kafka_broker)
    
    print(f"🔄 Metrics Refresh")
    print(f"   Redis: {args.redis_host}:{args.redis_port}")
    print(f"   Kafka: {args.kafka_broker} → {DISCOVERY_TOPIC}")
    
    try:
        while True:
            # Get tracked KOLs
            usernames = get_tracked_kols(r)
            print(f"\n📊 Found {len(usernames)} tracked KOLs")
            
            if usernames:
                # Push to discovery topic
                count = push_to_discovery(producer, usernames)
                print(f"   ✅ Pushed {count} usernames to {DISCOVERY_TOPIC}")
            else:
                print("   ⚠️ No tracked KOLs found in Redis")
            
            if args.interval <= 0:
                break
            
            print(f"   ⏰ Sleeping {args.interval}s...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\n👋 Stopped")
    finally:
        producer.close()


if __name__ == "__main__":
    main()

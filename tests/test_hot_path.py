"""
Test Hot Path Pipeline
======================

Script để test toàn bộ Hot Path flow:
1. Push test profile vào Kafka
2. Verify Spark job consume và process
3. Check output trong scores.stream topic
4. Check Redis cache

Usage:
    python test_hot_path.py --action push     # Push test data
    python test_hot_path.py --action consume  # Consume scores
    python test_hot_path.py --action all      # Full test
"""

import json
import time
import argparse
from datetime import datetime, timezone
from uuid import uuid4

# Kafka
try:
    from kafka import KafkaProducer, KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("⚠️ kafka-python not installed. Run: pip install kafka-python")

# Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ redis not installed. Run: pip install redis")


# Configuration
KAFKA_BROKER = "localhost:19092"
INPUT_TOPIC = "kol.profiles.raw"
OUTPUT_TOPIC = "scores.stream"
REDIS_HOST = "localhost"
REDIS_PORT = 16379


def create_test_profile(username: str = None, followers: int = None) -> dict:
    """Create a test profile event"""
    if username is None:
        username = f"test_user_{uuid4().hex[:8]}"
    
    if followers is None:
        import random
        followers = random.randint(1000, 1000000)
    
    return {
        "event_id": str(uuid4()),
        "event_time": datetime.now(timezone.utc).isoformat(),
        "event_type": "profile",
        "platform": "tiktok",
        "username": username,
        "user_id": f"uid_{uuid4().hex[:12]}",
        "followers_count": followers,
        "following_count": int(followers * 0.1),
        "post_count": int(followers * 0.01),
        "favorites_count": int(followers * 5),
        "verified": followers > 100000,
        "bio": f"Test KOL profile for {username}. Content creator and influencer.",
        "profile_url": f"https://www.tiktok.com/@{username}",
        "nickname": username.title(),
        "signature": "Follow me for more content!",
    }


def push_test_profiles(count: int = 5):
    """Push test profiles to Kafka"""
    if not KAFKA_AVAILABLE:
        print("❌ Kafka not available")
        return
    
    print(f"📤 Pushing {count} test profiles to {INPUT_TOPIC}...")
    
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8') if k else None,
    )
    
    test_profiles = [
        # Nano influencer (low followers)
        {"username": "nano_creator_001", "followers": 5000},
        # Micro influencer
        {"username": "micro_creator_002", "followers": 25000},
        # Mid-tier
        {"username": "mid_creator_003", "followers": 150000},
        # Macro
        {"username": "macro_creator_004", "followers": 800000},
        # Mega
        {"username": "mega_creator_005", "followers": 5000000},
    ]
    
    for i, profile_config in enumerate(test_profiles[:count]):
        profile = create_test_profile(
            username=profile_config["username"],
            followers=profile_config["followers"]
        )
        
        future = producer.send(
            INPUT_TOPIC,
            key=profile["username"],
            value=profile
        )
        result = future.get(timeout=10)
        
        print(f"  ✅ [{i+1}/{count}] {profile['username']} ({profile['followers_count']:,} followers)")
        print(f"     → Partition: {result.partition}, Offset: {result.offset}")
    
    producer.flush()
    producer.close()
    
    print(f"\n✅ Pushed {count} profiles to {INPUT_TOPIC}")


def consume_scores(timeout: int = 30):
    """Consume scores from output topic"""
    if not KAFKA_AVAILABLE:
        print("❌ Kafka not available")
        return
    
    print(f"📥 Consuming from {OUTPUT_TOPIC} (timeout: {timeout}s)...")
    
    consumer = KafkaConsumer(
        OUTPUT_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset='latest',
        consumer_timeout_ms=timeout * 1000,
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        key_deserializer=lambda k: k.decode('utf-8') if k else None,
    )
    
    count = 0
    start_time = time.time()
    
    print("\nWaiting for scores...\n")
    
    for message in consumer:
        count += 1
        score = message.value
        
        print(f"📊 Score #{count}:")
        print(f"   KOL: {score.get('kol_id')}")
        print(f"   Platform: {score.get('platform')}")
        print(f"   Trust: {score.get('trust_score', 'N/A')} ({score.get('trust_label', 'N/A')})")
        print(f"   Success: {score.get('success_score', 'N/A')} ({score.get('success_label', 'N/A')})")
        print(f"   Trending: {score.get('trending_score', 'N/A')} ({score.get('trending_label', 'N/A')})")
        print(f"   Latency: {score.get('latency_ms', 'N/A')}ms")
        print()
    
    elapsed = time.time() - start_time
    print(f"✅ Consumed {count} scores in {elapsed:.1f}s")
    
    consumer.close()


def check_redis_cache():
    """Check scores cached in Redis"""
    if not REDIS_AVAILABLE:
        print("❌ Redis not available")
        return
    
    print(f"🔍 Checking Redis cache at {REDIS_HOST}:{REDIS_PORT}...")
    
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        
        # Get all score keys
        keys = r.keys("kol:score:*")
        
        if not keys:
            print("   No scores cached yet")
            return
        
        print(f"\n📦 Found {len(keys)} cached scores:\n")
        
        for key in keys[:10]:  # Show first 10
            value = r.get(key)
            if value:
                score = json.loads(value)
                kol_id = key.replace("kol:score:", "")
                print(f"   {kol_id}:")
                print(f"      Trust: {score.get('trust_score', 'N/A')}")
                print(f"      Success: {score.get('success_score', 'N/A')}")
                print(f"      Trending: {score.get('trending_score', 'N/A')}")
                print(f"      Cached at: {score.get('timestamp', 'N/A')}")
                print()
        
        if len(keys) > 10:
            print(f"   ... and {len(keys) - 10} more")
            
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")


def check_kafka_topics():
    """Check Kafka topic status"""
    if not KAFKA_AVAILABLE:
        print("❌ Kafka not available")
        return
    
    print(f"📋 Checking Kafka topics at {KAFKA_BROKER}...")
    
    from kafka.admin import KafkaAdminClient
    
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BROKER)
        topics = admin.list_topics()
        
        relevant_topics = [t for t in topics if 'kol' in t or 'score' in t]
        
        print(f"\n   Relevant topics:")
        for topic in sorted(relevant_topics):
            print(f"      • {topic}")
            
        admin.close()
        
    except Exception as e:
        print(f"❌ Kafka admin failed: {e}")


def run_full_test():
    """Run full end-to-end test"""
    print("=" * 60)
    print("🧪 HOT PATH END-TO-END TEST")
    print("=" * 60)
    
    # Step 1: Check infrastructure
    print("\n📋 Step 1: Check Infrastructure")
    print("-" * 40)
    check_kafka_topics()
    
    # Step 2: Push test data
    print("\n📤 Step 2: Push Test Profiles")
    print("-" * 40)
    push_test_profiles(count=3)
    
    # Step 3: Wait for processing
    print("\n⏳ Step 3: Waiting for Spark processing...")
    print("-" * 40)
    print("   (Make sure Spark streaming job is running)")
    print("   Waiting 15 seconds...")
    time.sleep(15)
    
    # Step 4: Check output
    print("\n📥 Step 4: Check Output")
    print("-" * 40)
    consume_scores(timeout=10)
    
    # Step 5: Check Redis
    print("\n🔍 Step 5: Check Redis Cache")
    print("-" * 40)
    check_redis_cache()
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Test Hot Path Pipeline")
    parser.add_argument(
        "--action",
        choices=["push", "consume", "redis", "topics", "all"],
        default="all",
        help="Action to perform"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of test profiles to push"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Consumer timeout in seconds"
    )
    
    args = parser.parse_args()
    
    if args.action == "push":
        push_test_profiles(count=args.count)
    elif args.action == "consume":
        consume_scores(timeout=args.timeout)
    elif args.action == "redis":
        check_redis_cache()
    elif args.action == "topics":
        check_kafka_topics()
    elif args.action == "all":
        run_full_test()


if __name__ == "__main__":
    main()

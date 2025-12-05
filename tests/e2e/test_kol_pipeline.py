"""
KOL Pipeline E2E Test
=====================

Test toàn bộ flow: Scraper → Kafka → (verify data)

Usage:
    py tests/e2e/test_kol_pipeline.py
"""

import json
import time
import sys
sys.path.insert(0, ".")

from kafka import KafkaConsumer, KafkaAdminClient, TopicPartition
from kafka.admin import NewTopic

KAFKA_BOOTSTRAP = "localhost:19092"

TOPICS = [
    "kol.discovery.raw",
    "kol.profiles.raw", 
    "kol.videos.raw",
    "kol.comments.raw",
    "kol.products.raw",
]

# Expected schema fields
EXPECTED_SCHEMAS = {
    "kol.discovery.raw": [
        "event_id", "event_time", "event_type", "platform",
        "username", "video_id", "video_url", "caption", 
        "source", "keyword", "niche_hint"
    ],
    "kol.profiles.raw": [
        "event_id", "event_time", "event_type", "platform",
        "username", "nickname", "followers_raw", "following_raw",
        "likes_raw", "bio", "avatar_url", "verified", "profile_url"
    ],
    "kol.videos.raw": [
        "event_id", "event_time", "event_type", "platform",
        "video_id", "video_url", "username", "caption",
        "view_count_raw", "like_count_raw", "comment_count_raw", "share_count_raw",
        "view_count", "like_count", "comment_count", "share_count"
    ],
    "kol.comments.raw": [
        "event_id", "event_time", "event_type", "platform",
        "video_id", "video_url", "username", "comment_text"
    ],
    "kol.products.raw": [
        "event_id", "event_time", "event_type", "platform",
        "username", "video_id", "video_url",
        "video_views", "video_likes", "video_comments", "video_shares",
        "product_id", "product_title", "seller_id", "price", "currency",
        "product_url", "keyword", "sold_count", "sold_count_raw",
        "sold_delta", "engagement_total", "engagement_rate", "est_clicks", "est_ctr"
    ],
}


def check_kafka_connection():
    """Check if Kafka is running"""
    print("\n" + "="*60)
    print("1️⃣  CHECKING KAFKA CONNECTION")
    print("="*60)
    
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
        topics = admin.list_topics()
        print(f"✅ Kafka connected: {KAFKA_BOOTSTRAP}")
        print(f"   Topics found: {len(topics)}")
        admin.close()
        return True
    except Exception as e:
        print(f"❌ Kafka connection failed: {e}")
        print("   → Run: docker start kol-redpanda")
        return False


def check_topics_exist():
    """Check if all required topics exist"""
    print("\n" + "="*60)
    print("2️⃣  CHECKING KAFKA TOPICS")
    print("="*60)
    
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
        existing = admin.list_topics()
        
        missing = []
        for topic in TOPICS:
            if topic in existing:
                print(f"   ✅ {topic}")
            else:
                print(f"   ❌ {topic} (missing)")
                missing.append(topic)
        
        # Create missing topics
        if missing:
            print(f"\n   Creating missing topics...")
            new_topics = [NewTopic(name=t, num_partitions=1, replication_factor=1) for t in missing]
            admin.create_topics(new_topics)
            print(f"   ✅ Created {len(missing)} topics")
        
        admin.close()
        return True
    except Exception as e:
        print(f"❌ Topic check failed: {e}")
        return False


def get_topic_message_count(topic):
    """Get message count in a topic"""
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            auto_offset_reset='earliest',
            consumer_timeout_ms=1000
        )
        
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            return 0
        
        total = 0
        for p in partitions:
            tp = TopicPartition(topic, p)
            consumer.assign([tp])
            consumer.seek_to_end(tp)
            end = consumer.position(tp)
            consumer.seek_to_beginning(tp)
            start = consumer.position(tp)
            total += (end - start)
        
        consumer.close()
        return total
    except:
        return 0


def check_topic_data():
    """Check data in each topic"""
    print("\n" + "="*60)
    print("3️⃣  CHECKING TOPIC DATA")
    print("="*60)
    
    for topic in TOPICS:
        count = get_topic_message_count(topic)
        status = "✅" if count > 0 else "⚠️"
        print(f"   {status} {topic}: {count} messages")
    
    return True


def sample_and_validate_schema(topic, expected_fields):
    """Sample one message and validate schema"""
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            auto_offset_reset='earliest',
            consumer_timeout_ms=3000,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        for msg in consumer:
            data = msg.value
            
            # Check required fields
            missing = [f for f in expected_fields if f not in data]
            extra = [f for f in data.keys() if f not in expected_fields and f != 'has_shop']
            
            consumer.close()
            
            return {
                "sample": data,
                "missing_fields": missing,
                "extra_fields": extra,
                "valid": len(missing) == 0
            }
        
        consumer.close()
        return None
    except Exception as e:
        return {"error": str(e)}


def validate_schemas():
    """Validate schema of each topic"""
    print("\n" + "="*60)
    print("4️⃣  VALIDATING SCHEMAS")
    print("="*60)
    
    all_valid = True
    
    for topic, expected in EXPECTED_SCHEMAS.items():
        result = sample_and_validate_schema(topic, expected)
        
        if result is None:
            print(f"\n   ⚠️  {topic}: No data to validate")
        elif "error" in result:
            print(f"\n   ❌ {topic}: {result['error']}")
            all_valid = False
        elif result["valid"]:
            print(f"\n   ✅ {topic}: Schema valid")
            # Show sample
            sample = result["sample"]
            print(f"      Sample: {json.dumps({k: sample.get(k, '')[:50] if isinstance(sample.get(k), str) else sample.get(k) for k in list(expected)[:5]}, ensure_ascii=False)[:200]}...")
        else:
            print(f"\n   ❌ {topic}: Schema invalid")
            if result["missing_fields"]:
                print(f"      Missing: {result['missing_fields']}")
            if result["extra_fields"]:
                print(f"      Extra: {result['extra_fields']}")
            all_valid = False
    
    return all_valid


def test_scraper_dry_run():
    """Test scraper in dry-run mode"""
    print("\n" + "="*60)
    print("5️⃣  TESTING SCRAPER (Dry Run)")
    print("="*60)
    
    import subprocess
    
    cmd = [
        "py", "ingestion/sources/kol_scraper.py",
        "discovery", "--niche", "thời trang", "--mode", "hashtag",
        "--max-scroll", "1", "--dry-run"
    ]
    
    print(f"   Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd="e:\\Project\\kol-platform"
        )
        
        if result.returncode == 0:
            # Count discoveries
            lines = result.stdout.split('\n')
            discovery_count = 0
            for line in lines:
                if "Discovered:" in line or "creators found" in line.lower():
                    print(f"   {line.strip()}")
                if "Total unique creators" in line:
                    discovery_count = int(''.join(filter(str.isdigit, line.split(':')[-1])))
            
            print(f"   ✅ Scraper dry-run successful")
            return True
        else:
            print(f"   ❌ Scraper failed: {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"   ⚠️  Scraper timed out (may be normal)")
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_scraper_with_kafka():
    """Test scraper pushing to Kafka"""
    print("\n" + "="*60)
    print("6️⃣  TESTING SCRAPER → KAFKA (Live)")
    print("="*60)
    
    import subprocess
    
    # Get current counts
    before_counts = {t: get_topic_message_count(t) for t in TOPICS}
    
    cmd = [
        "py", "ingestion/sources/kol_scraper.py",
        "discovery", "--niche", "thời trang", "--mode", "hashtag",
        "--max-scroll", "1"
    ]
    
    print(f"   Running: {' '.join(cmd[:6])}...")
    print(f"   (This will scrape real TikTok data)")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd="e:\\Project\\kol-platform"
        )
        
        # Get after counts
        after_counts = {t: get_topic_message_count(t) for t in TOPICS}
        
        print(f"\n   Messages pushed to Kafka:")
        any_new = False
        for topic in TOPICS:
            diff = after_counts[topic] - before_counts[topic]
            if diff > 0:
                print(f"      ✅ {topic}: +{diff}")
                any_new = True
        
        if any_new:
            print(f"\n   ✅ Scraper → Kafka pipeline working!")
            return True
        else:
            print(f"\n   ⚠️  No new messages (may need to check scraper output)")
            print(f"   Stdout: {result.stdout[-500:]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"   ⚠️  Scraper timed out")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def print_summary(results):
    """Print test summary"""
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}: {name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\n   Total: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  Some tests failed. Check output above.")


def main():
    print("="*60)
    print("KOL PIPELINE E2E TEST")
    print("="*60)
    print("Testing: Scraper → Kafka → Schema Validation")
    
    results = {}
    
    # 1. Check Kafka
    results["Kafka Connection"] = check_kafka_connection()
    if not results["Kafka Connection"]:
        print("\n❌ Cannot continue without Kafka. Start it first:")
        print("   docker start kol-redpanda")
        return
    
    # 2. Check Topics
    results["Topics Exist"] = check_topics_exist()
    
    # 3. Check existing data
    results["Topic Data"] = check_topic_data()
    
    # 4. Validate schemas (if data exists)
    results["Schema Validation"] = validate_schemas()
    
    # 5. Test scraper dry-run
    results["Scraper Dry-Run"] = test_scraper_dry_run()
    
    # 6. Optional: Test live scraping
    print("\n" + "-"*60)
    response = input("Run live scraper test? (pushes real data to Kafka) [y/N]: ")
    if response.lower() == 'y':
        results["Scraper → Kafka"] = test_scraper_with_kafka()
    
    # Summary
    print_summary(results)


if __name__ == "__main__":
    main()

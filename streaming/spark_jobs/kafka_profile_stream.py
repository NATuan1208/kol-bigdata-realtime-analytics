"""
Profile Metrics Stream (Spark Structured Streaming)
---------------------------------------------------

Reads `kol.profiles.raw` Kafka topic and updates profile metrics in Redis.

This is a separate stream from videos because:
- Profile updates are less frequent than video updates
- Spark Streaming can't join 2 streams with aggregation easily
- Cleaner to separate concerns

Flow:
  Scraper → kol.profiles.raw (Kafka) → Spark → Redis (kol_profile:{username})

Redis Schema:
  Key: kol_profile:{username}
  Hash fields:
    - followers, following, total_likes: current values
    - followers_vel, total_likes_vel: velocity (growth rate)
    - ts: timestamp
"""

import os
from typing import Any
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, to_timestamp, expr
from pyspark.sql.types import StructType, StructField, StringType, IntegerType


# ---------------------- Configuration ----------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC_PROFILES", "kol.profiles.raw")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TTL = int(os.getenv("REDIS_TTL_SECONDS", "3600"))

CHECKPOINT = os.getenv("CHECKPOINT_BASE", "/tmp/checkpoints/kol-profiles")
TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL", "30 seconds")


# ---------------------- Schema ----------------------
# Support both TikTok (string format) and YouTube (integer format)
PROFILE_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("username", StringType(), True),
    StructField("channel_id", StringType(), True),  # YouTube channel_id
    StructField("nickname", StringType(), True),
    # TikTok format (string)
    StructField("followers_raw", StringType(), True),
    StructField("following_raw", StringType(), True),
    StructField("likes_raw", StringType(), True),
    # YouTube format (integer)
    StructField("followers", IntegerType(), True),  # YouTube: direct integer
    StructField("total_videos", IntegerType(), True),
    StructField("total_views", IntegerType(), True),
    StructField("description", StringType(), True),
    # Common fields
    StructField("bio", StringType(), True),
    StructField("avatar_url", StringType(), True),
    StructField("verified", StringType(), True),
    StructField("profile_url", StringType(), True),
])


def create_spark_session():
    spark = SparkSession.builder \
        .appName("KOL-Profiles-STREAM") \
        .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except Exception:
        return 0


def parse_count_string(s: str) -> int:
    """Parse TikTok count strings like '852.3K', '33.6M' to int"""
    if not s or s == "0":
        return 0
    
    s = s.strip().upper()
    multiplier = 1
    
    if s.endswith('K'):
        multiplier = 1000
        s = s[:-1]
    elif s.endswith('M'):
        multiplier = 1000000
        s = s[:-1]
    elif s.endswith('B'):
        multiplier = 1000000000
        s = s[:-1]
    
    try:
        return int(float(s) * multiplier)
    except:
        return 0


def foreach_batch_update_redis(batch_df, batch_id):
    """Process profiles and update Redis"""
    try:
        import redis
    except ImportError:
        print("⚠️ redis package not found in Spark driver.")
        return

    valid_df = batch_df.filter(col("username").isNotNull())
    
    if valid_df.count() == 0:
        print(f"Batch {batch_id}: No valid profile data")
        return

    rows = valid_df.collect()
    if not rows:
        return

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    
    updated_count = 0
    for row in rows:
        username = row["username"]
        if not username:
            continue
        
        platform = row.get("platform", "tiktok")
        channel_id = row.get("channel_id", "")  # YouTube channel_id (optional)
        ts = row["event_time"] if row["event_time"] is not None else datetime.utcnow().isoformat()
        
        # Support both TikTok (string) and YouTube (integer) formats
        if platform == "youtube":
            # YouTube format: direct integers
            followers = safe_int(row.get("followers", 0))
            following = 0  # YouTube doesn't track following
            total_likes = safe_int(row.get("total_views", 0))  # Use total_views as engagement proxy
        else:
            # TikTok format: parse string "852.3K" → 852300
            followers = parse_count_string(row.get("followers_raw", "0"))
            following = parse_count_string(row.get("following_raw", "0"))
            total_likes = parse_count_string(row.get("likes_raw", "0"))

        # ========== Calculate velocity ==========
        key = f"kol_profile:{username}"
        prev = r.hgetall(key)
        
        prev_followers = safe_int(prev.get("followers"))
        prev_total_likes = safe_int(prev.get("total_likes"))
        
        followers_vel = max(0, followers - prev_followers) if prev_followers > 0 else followers
        total_likes_vel = max(0, total_likes - prev_total_likes) if prev_total_likes > 0 else total_likes

        # ========== Store to Redis ==========
        mapping = {
            "followers": int(followers),
            "following": int(following),
            "total_likes": int(total_likes),
            "followers_vel": int(followers_vel),
            "total_likes_vel": int(total_likes_vel),
            "platform": str(platform),
            "ts": str(ts)
        }
        
        # Add channel_id for YouTube
        if channel_id:
            mapping["channel_id"] = str(channel_id)

        try:
            r.hset(key, mapping=mapping)
            r.expire(key, REDIS_TTL)
            updated_count += 1
        except Exception as e:
            print(f"Error writing profile to Redis for {username}: {e}")
    
    print(f"✅ Batch {batch_id}: Updated {updated_count} profiles in Redis")


def main():
    print("🚀 Starting KOL Profiles Stream")
    print(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS} topic={KAFKA_TOPIC}")
    print(f"Redis: {REDIS_HOST}:{REDIS_PORT} db={REDIS_DB}")
    print("Press Ctrl+C to stop")

    spark = create_spark_session()

    stream_df = spark.readStream.format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .load()

    parsed = stream_df.select(
        from_json(col("value").cast("string"), PROFILE_SCHEMA).alias("data")
    ).select("data.*")

    query = parsed.writeStream \
        .trigger(processingTime=TRIGGER_INTERVAL) \
        .option("checkpointLocation", f"{CHECKPOINT}/profiles") \
        .foreachBatch(foreach_batch_update_redis) \
        .start()

    try:
        query.awaitTermination()
    except KeyboardInterrupt:
        print("Stopping profiles stream...")
        query.stop()


if __name__ == "__main__":
    main()
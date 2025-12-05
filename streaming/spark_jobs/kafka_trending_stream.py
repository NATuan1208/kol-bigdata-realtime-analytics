"""
KOL Trending Stream (Spark Structured Streaming)
------------------------------------------------

Reads `kol.videos.raw` Kafka topic, aggregates metrics per
`username` per micro-batch, computes velocity vs previous snapshot
stored in Redis, computes a TrendingScore and writes results back to
Redis for low-latency dashboards.

Design:
- Each micro-batch: aggregate SUM of all video metrics per username
- Read previous snapshot from Redis, compute velocity = now - prev
- Trending = ALPHA*view_vel + BETA*like_vel + GAMMA*share_vel
- Store back into Redis hash `streaming_scores:{username}` with fields
  score, view, like, share, video_count, ts

Business Logic:
- SUM all video metrics → Track tổng engagement của KOL (không chỉ 1 video)
- Velocity = tốc độ tăng engagement giữa 2 micro-batch
- Score cao = KOL đang trending (engagement tăng nhanh)

Notes:
- This job expects `redis` Python package to be available in the Spark
  driver container. Install with `pip install redis` inside the
  `kol-spark-master` container or ship a wheel via `--py-files`.
- Configurable via environment variables listed below.
"""

import os
import json
from datetime import datetime
from typing import Any

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp, to_timestamp, expr
from pyspark.sql.types import StructType, StructField, StringType, IntegerType


# ---------------------- Configuration ----------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "kol.videos.raw")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TTL = int(os.getenv("REDIS_TTL_SECONDS", "3600"))

ALPHA = float(os.getenv("TREND_ALPHA", "1.0"))
BETA = float(os.getenv("TREND_BETA", "0.5"))
GAMMA = float(os.getenv("TREND_GAMMA", "0.2"))

CHECKPOINT = os.getenv("CHECKPOINT_BASE", "/tmp/checkpoints/kol-trending")
TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL", "30 seconds")


# ---------------------- Schema ----------------------
VIDEO_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_time", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("platform", StringType(), False),
    StructField("video_id", StringType(), True),
    StructField("video_url", StringType(), True),
    StructField("username", StringType(), True),
    StructField("caption", StringType(), True),
    StructField("view_count", IntegerType(), True),
    StructField("like_count", IntegerType(), True),
    StructField("share_count", IntegerType(), True),
])


def create_spark_session():
    spark = SparkSession.builder \
        .appName("KOL-Trending-STREAM") \
        .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except Exception:
        return 0


def foreach_batch_update_redis(batch_df, batch_id):
    # lightweight import so job works even if redis not present at module import
    try:
        import redis
    except ImportError:
        print("⚠️ redis package not found in Spark driver. Install 'redis' in container.")
        return

    # Filter out null usernames
    valid_df = batch_df.filter(col("username").isNotNull())
    
    if valid_df.count() == 0:
        print(f"Batch {batch_id}: No valid data")
        return

    # Aggregate TỔNG metrics per username (không phải MAX)
    # Tính SUM để track tổng engagement của tất cả videos
    agg = valid_df.groupBy("username").agg(
        expr("sum(view_count) as view_now"),      # Tổng views tất cả videos
        expr("sum(like_count) as like_now"),      # Tổng likes
        expr("sum(share_count) as share_now"),    # Tổng shares
        expr("count(*) as video_count"),          # Số videos trong batch
        expr("max(event_timestamp) as ts")        # Thời điểm mới nhất
    )

    rows = agg.collect()
    if not rows:
        return

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    
    updated_count = 0
    for row in rows:
        username = row["username"]
        if not username:
            continue
            
        view_now = safe_int(row["view_now"])
        like_now = safe_int(row["like_now"])
        share_now = safe_int(row["share_now"])
        video_count = safe_int(row["video_count"])
        ts = row["ts"] if row["ts"] is not None else datetime.utcnow().isoformat()

        key = f"streaming_scores:{username}"

        # Get previous snapshot từ Redis
        prev = r.hgetall(key)
        prev_view = safe_int(prev.get("view"))
        prev_like = safe_int(prev.get("like"))
        prev_share = safe_int(prev.get("share"))

        # Calculate velocity (tốc độ tăng)
        # Nếu lần đầu (prev = 0), velocity = current values
        view_vel = max(0, view_now - prev_view) if prev_view > 0 else view_now
        like_vel = max(0, like_now - prev_like) if prev_like > 0 else like_now
        share_vel = max(0, share_now - prev_share) if prev_share > 0 else share_now

        # Trending score = weighted sum of velocities
        score = ALPHA * view_vel + BETA * like_vel + GAMMA * share_vel

        # Store as hash
        mapping = {
            "score": float(score),
            "view": int(view_now),
            "like": int(like_now),
            "share": int(share_now),
            "video_count": int(video_count),
            "view_vel": int(view_vel),
            "like_vel": int(like_vel),
            "share_vel": int(share_vel),
            "ts": str(ts)
        }

        try:
            r.hset(key, mapping=mapping)
            r.expire(key, REDIS_TTL)
            updated_count += 1
        except Exception as e:
            print(f"Error writing to Redis for {username}: {e}")
    
    print(f"Batch {batch_id}: Updated {updated_count} KOLs in Redis")


def main():
    print("🚀 Starting KOL Trending Stream")
    print(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS} topic={KAFKA_TOPIC}")
    print(f"Redis: {REDIS_HOST}:{REDIS_PORT} db={REDIS_DB}")
    print(f"Alpha/Beta/Gamma = {ALPHA}/{BETA}/{GAMMA}")
    print("Press Ctrl+C to stop")

    spark = create_spark_session()

    stream_df = spark.readStream.format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .load()

    parsed = stream_df.select(
        from_json(col("value").cast("string"), VIDEO_SCHEMA).alias("data")
    ).select("data.*")

    # ensure event_timestamp
    parsed = parsed.withColumn("event_timestamp", to_timestamp(col("event_time")))

    query = parsed.writeStream \
        .trigger(processingTime=TRIGGER_INTERVAL) \
        .option("checkpointLocation", f"{CHECKPOINT}/videos") \
        .foreachBatch(foreach_batch_update_redis) \
        .start()

    try:
        query.awaitTermination()
    except KeyboardInterrupt:
        print("Stopping trending stream...")
        query.stop()


if __name__ == "__main__":
    main()

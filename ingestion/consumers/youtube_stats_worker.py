"""
YouTube Stats Worker

Consumer lắng nghe kol.discovery.raw (platform="youtube")
→ Gọi YouTube API lấy:
  - Channel info (subscribers, videos, views)
  - Top 50 videos stats
→ Push lên:
  - kol.profiles.raw
  - kol.videos.raw

100% API, không Selenium → NHANH!

Chạy:
    python -m ingestion.consumers.youtube_stats_worker --max-videos 50
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict

from kafka import KafkaConsumer, KafkaProducer

# Import YouTube API
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources.youtube_api import YouTubeAPI

# Config
KAFKA_BROKER = "localhost:19092"
INPUT_TOPIC = "kol.discovery.raw"
OUTPUT_TOPIC_VIDEOS = "kol.videos.raw"
OUTPUT_TOPIC_PROFILES = "kol.profiles.raw"
CONSUMER_GROUP = "youtube-stats-worker-v1"


class YouTubeStatsWorker:
    """YouTube Stats Worker - 100% API"""
    
    def __init__(self, max_videos: int = 50, start_delay: int = 0):
        self.max_videos = max_videos
        self.start_delay = start_delay
        self.api = YouTubeAPI()
        self.consumer = None
        self.producer = None
        self.running = True
    
    def connect_kafka(self, broker: str):
        """Connect to Kafka"""
        print(f"\n📥 Connecting to Kafka consumer...")
        self.consumer = KafkaConsumer(
            INPUT_TOPIC,
            bootstrap_servers=broker,
            group_id=CONSUMER_GROUP,
            auto_offset_reset='latest',
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        print(f"   ✅ Connected to {broker}")
        print(f"   ℹ️  Reading from: LATEST (new messages only)")
        
        print(f"\n📤 Connecting to Kafka producer...")
        self.producer = KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda m: json.dumps(m).encode('utf-8')
        )
        print(f"   ✅ Producer ready")
    
    def process_message(self, message: Dict) -> bool:
        """
        Process discovery message
        Returns: True if processed successfully
        """
        # Filter platform
        platform = message.get("platform", "tiktok")
        if platform != "youtube":
            return False  # Skip TikTok messages
        
        username = message.get("username", "")
        channel_id = message.get("channel_id", "")
        event_type = message.get("event_type", "discovery")
        
        if not username:
            return False
        
        # Log
        if event_type == "refresh":
            print(f"\n🔄 Refreshing @{username}")
        else:
            print(f"\n🆕 Processing @{username}")
        
        # Get channel info - try channel_id first, then resolve by handle
        channel = None
        if channel_id:
            channel = self.api.get_channel_info(channel_id)
        
        # If no channel_id or lookup failed, resolve by username/handle
        if not channel:
            print(f"   🔍 Resolving channel by handle: @{username}")
            channel = self.api.get_channel_by_handle(username)
        
        if not channel:
            print(f"   ❌ Channel not found for @{username}")
            return False
        
        # Update channel_id from resolved channel
        channel_id = channel.channel_id
        
        print(f"   ✅ Profile: {channel.subscribers:,} subscribers")
        
        # Push profile to Kafka
        self._push_profile(channel)
        
        # 2. Get videos
        video_ids = self.api.get_channel_videos(channel_id, self.max_videos)
        print(f"   📹 Found {len(video_ids)} videos")
        
        if not video_ids:
            return True
        
        # 3. Get video stats
        videos = self.api.get_video_stats(video_ids)
        
        # Push videos to Kafka
        for video in videos:
            video.username = username  # Set username
            self._push_video(video)
        
        print(f"   ✅ Scraped {len(videos)} video stats")
        
        return True
    
    def _push_profile(self, channel):
        """Push channel profile to Kafka"""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "profile",
            "platform": "youtube",
            "username": channel.username,
            "channel_id": channel.channel_id,
            "channel_title": channel.title,
            "followers_raw": str(channel.subscribers),  # Convert to string for Spark compatibility
            "following_raw": "0",  # YouTube doesn't have following
            "likes_raw": str(channel.total_views),  # Use total_views as proxy
            "bio": channel.description or "",
            "avatar_url": channel.avatar_url,
            "verified": "false",  # Can add later if API provides
            "profile_url": f"https://youtube.com/@{channel.username}",
            # Keep original fields for backward compatibility
            "total_videos": channel.total_videos,
            "published_at": channel.published_at
        }
        
        self.producer.send(
            OUTPUT_TOPIC_PROFILES,
            key=channel.username.encode('utf-8'),
            value=event
        )
    
    def _push_video(self, video):
        """Push video stats to Kafka"""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "video",
            "platform": "youtube",
            "username": video.username,
            "video_id": video.video_id,
            "video_url": f"https://youtube.com/watch?v={video.video_id}",
            "title": video.title,
            "description": video.description[:500],  # Limit length
            "view_count": video.view_count,
            "like_count": video.like_count,
            "comment_count": video.comment_count,  # YouTube có comment_count, TikTok dùng share_count
            "duration": video.duration,
            "published_at": video.published_at,
            "thumbnail_url": video.thumbnail_url
        }
        
        self.producer.send(
            OUTPUT_TOPIC_VIDEOS,
            key=video.video_id.encode('utf-8'),
            value=event
        )
    
    def run(self):
        """Run worker loop"""
        if self.start_delay > 0:
            print(f"\n⏳ Starting in {self.start_delay}s...")
            time.sleep(self.start_delay)
        
        print(f"\n✅ Consumer started! Waiting for messages...")
        print(f"   (Press Ctrl+C to stop)")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    self.process_message(message.value)
                except Exception as e:
                    print(f"   ❌ Error processing message: {e}")
                    continue
        
        except KeyboardInterrupt:
            print(f"\n\n👋 Stopped by user")
        
        finally:
            self.consumer.close()
            self.producer.close()
            print(f"\n📊 Total API quota used: {self.api.get_quota_used()} units")


def main():
    parser = argparse.ArgumentParser(description="YouTube Stats Worker")
    parser.add_argument("--max-videos", type=int, default=50, help="Max videos per channel")
    parser.add_argument("--start-delay", type=int, default=0, help="Delay before starting (seconds)")
    parser.add_argument("--kafka-broker", default=KAFKA_BROKER)
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  YOUTUBE STATS WORKER")
    print(f"{'='*60}")
    print(f"\n  Config:")
    print(f"    Kafka Broker: {args.kafka_broker}")
    print(f"    Input Topic: {INPUT_TOPIC}")
    print(f"    Output Topics: {OUTPUT_TOPIC_VIDEOS}, {OUTPUT_TOPIC_PROFILES}")
    print(f"    Consumer Group: {CONSUMER_GROUP}")
    print(f"    Max Videos: {args.max_videos}")
    print(f"    Start Delay: {args.start_delay}s")
    print(f"{'='*60}")
    
    worker = YouTubeStatsWorker(
        max_videos=args.max_videos,
        start_delay=args.start_delay
    )
    
    worker.connect_kafka(args.kafka_broker)
    worker.run()


if __name__ == "__main__":
    main()

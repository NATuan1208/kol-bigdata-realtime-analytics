"""
YouTube Comments Worker

Consumer lắng nghe kol.videos.raw (platform="youtube")
→ Gọi YouTube API lấy top comments
→ Push lên kol.comments.raw

100% API, không Selenium

Chạy:
    python -m ingestion.consumers.youtube_comments_worker --max-comments 100
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict

from kafka import KafkaConsumer, KafkaProducer

# Import YouTube API
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources.youtube_api import YouTubeAPI

# Config
KAFKA_BROKER = "localhost:19092"
INPUT_TOPIC = "kol.videos.raw"
OUTPUT_TOPIC = "kol.comments.raw"
CONSUMER_GROUP = "youtube-comments-worker-v1"


class YouTubeCommentsWorker:
    """YouTube Comments Worker - 100% API"""
    
    def __init__(self, max_comments: int = 100, start_delay: int = 0, delay_between_videos: float = 0):
        self.max_comments = max_comments
        self.start_delay = start_delay
        self.delay_between_videos = delay_between_videos
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
        
        print(f"\n📤 Connecting to Kafka producer...")
        self.producer = KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda m: json.dumps(m).encode('utf-8')
        )
        print(f"   ✅ Producer ready")
    
    def process_message(self, message: Dict) -> bool:
        """Process video message"""
        # Filter platform
        platform = message.get("platform", "tiktok")
        if platform != "youtube":
            return False
        
        video_id = message.get("video_id", "")
        username = message.get("username", "")
        
        if not video_id:
            return False
        
        print(f"\n💬 Getting comments for video {video_id} (@{username})")
        
        # Get comments
        comments = self.api.get_comments(video_id, self.max_comments)
        
        if not comments:
            print(f"   ⏭️  No comments (might be disabled)")
            # Still apply delay even if no comments
            if self.delay_between_videos > 0:
                time.sleep(self.delay_between_videos)
            return True
        
        # Push comments to Kafka
        for comment in comments:
            comment.username = username
            comment.video_id = video_id
            self._push_comment(comment)
        
        print(f"   ✅ {len(comments)} comments")
        
        # Optional delay between videos (rate limiting)
        if self.delay_between_videos > 0:
            time.sleep(self.delay_between_videos)
        
        return True
    
    def _push_comment(self, comment):
        """Push comment to Kafka"""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "comment",
            "platform": "youtube",
            "video_id": comment.video_id,
            "username": comment.username,
            "comment_id": comment.comment_id,
            "author": comment.author,
            "text": comment.text,
            "like_count": comment.like_count,
            "published_at": comment.published_at
        }
        
        self.producer.send(
            OUTPUT_TOPIC,
            key=comment.comment_id.encode('utf-8'),
            value=event
        )
    
    def run(self):
        """Run worker loop"""
        if self.start_delay > 0:
            print(f"\n⏳ Starting in {self.start_delay}s...")
            time.sleep(self.start_delay)
        
        print(f"\n✅ Consumer started! Waiting for messages...")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    self.process_message(message.value)
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    continue
        
        except KeyboardInterrupt:
            print(f"\n\n👋 Stopped by user")
        
        finally:
            self.consumer.close()
            self.producer.close()
            print(f"\n📊 Total API quota used: {self.api.get_quota_used()} units")


def main():
    parser = argparse.ArgumentParser(description="YouTube Comments Worker")
    parser.add_argument("--max-comments", type=int, default=100)
    parser.add_argument("--start-delay", type=int, default=0)
    parser.add_argument("--delay-between-videos", type=float, default=0, 
                        help="Delay in seconds between processing each video (default: 0)")
    parser.add_argument("--kafka-broker", default=KAFKA_BROKER)
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  YOUTUBE COMMENTS WORKER")
    print(f"{'='*60}")
    print(f"\n  Config:")
    print(f"    Kafka: {args.kafka_broker}")
    print(f"    Input: {INPUT_TOPIC}")
    print(f"    Output: {OUTPUT_TOPIC}")
    print(f"    Max Comments: {args.max_comments}")
    if args.delay_between_videos > 0:
        print(f"    Delay Between Videos: {args.delay_between_videos}s")
    print(f"{'='*60}")
    
    worker = YouTubeCommentsWorker(
        max_comments=args.max_comments,
        start_delay=args.start_delay,
        delay_between_videos=args.delay_between_videos
    )
    
    worker.connect_kafka(args.kafka_broker)
    worker.run()


if __name__ == "__main__":
    main()

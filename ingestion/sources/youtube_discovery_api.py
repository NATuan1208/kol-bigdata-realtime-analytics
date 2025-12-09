"""
YouTube Discovery - Find trending YouTube channels via API

API-based discovery (NO SELENIUM):
- Uses YouTube Data API v3: videos.list with chart=mostPopular
- Extracts channels from trending videos
- Push discoveries to Kafka topic: kol.discovery.raw

Message format:
{
    "event_id": "uuid",
    "event_time": "2024-01-01T00:00:00Z",
    "event_type": "discovery",
    "platform": "youtube",
    "username": "mrbeast",
    "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
    "url": "https://www.youtube.com/@mrbeast",
    "metadata": {
        "source": "api_trending",
        "discovery_video": "https://www.youtube.com/watch?v=xxx"
    }
}

Usage:
    # Dry run (test without pushing to Kafka)
    python -m ingestion.sources.youtube_discovery_api --dry-run
    
    # One-time discovery
    python -m ingestion.sources.youtube_discovery_api --max-channels 20

    # Daemon mode (continuous, every 6 hours)
    python -m ingestion.sources.youtube_discovery_api daemon --interval 21600
"""

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List

from kafka import KafkaProducer
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Config
KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
DISCOVERY_TOPIC = "kol.discovery.raw"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# API Config
DEFAULT_REGION = "VN"  # Vietnam
MAX_API_RESULTS = 50  # Max videos to fetch per request


@dataclass
class YouTubeDiscovery:
    channel_handle: str
    channel_id: str
    channel_url: str
    video_url: str
    source: str


def get_seed_channels(max_channels: int = 10) -> List[YouTubeDiscovery]:
    """
    Fallback: Return popular channels as seed data
    Used when API fails or as backup
    """
    print(f"   📋 Using seed channels (fallback)...")
    
    popular_channels = [
        {"handle": "mrbeast", "id": "UCX6OQ3DkcsbYNE6H8uQQuVA"},
        {"handle": "pewdiepie", "id": "UC-lHJZR3Gqxm24_Vd_AJ5Yw"},
        {"handle": "markiplier", "id": "UC7_YxT-KID8kRbqZo7MyscQ"},
        {"handle": "dude-perfect", "id": "UCRijo3ddMTht_IHyNSNXpNQ"},
        {"handle": "watcher", "id": "UC9X-G6FfgXMqDa-3Qa5Y2Ww"},
        {"handle": "sssniperwolf", "id": "UCpB959t8iPrxQWj7G6n0ctQ"},
        {"handle": "jacksepticeye", "id": "UCYzPXprvl5Y-Sf0g4vX-m6g"},
        {"handle": "vanossgaming", "id": "UCKqH_9mk1waLgBiL2vT5b9g"},
        {"handle": "kimpossiblefact", "id": "UCjBp_7RuDBUYbd1LegWEJ8g"},
        {"handle": "wwehd", "id": "UCJ5v_MCY6GNUBTO8-D3XoAg"}
    ]
    
    discoveries = []
    for ch in popular_channels[:max_channels]:
        channel_handle = ch["handle"]
        channel_id = ch["id"]
        
        discoveries.append(YouTubeDiscovery(
            channel_handle=channel_handle,
            channel_id=channel_id,
            channel_url=f"https://www.youtube.com/@{channel_handle}",
            video_url="",
            source="seed_channels"
        ))
        
        print(f"      ✅ @{channel_handle}")
    
    return discoveries


def discover_trending_channels_api(api_key: str, max_channels: int = 10, region: str = DEFAULT_REGION) -> List[YouTubeDiscovery]:
    """
    Discover trending channels via YouTube Data API v3 (NO SELENIUM!)
    
    Uses videos.list with chart=mostPopular to find trending videos,
    then extracts unique channels.
    
    Cost: ~101 quota units per request
    
    Args:
        api_key: YouTube Data API v3 key
        max_channels: Max channels to return
        region: Region code (VN, US, etc.)
    
    Returns:
        List of YouTubeDiscovery objects
    """
    print(f"\n   🌐 Fetching trending videos from YouTube API (region={region})...")
    
    if not api_key:
        print(f"      ⚠️  No API key provided!")
        return get_seed_channels(max_channels)
    
    try:
        # Build YouTube API client
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Get most popular videos
        request = youtube.videos().list(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode=region,
            maxResults=MAX_API_RESULTS
        )
        response = request.execute()
        
        if 'items' not in response or len(response['items']) == 0:
            print(f"      ⚠️  No trending videos found!")
            return get_seed_channels(max_channels)
        
        # Extract unique channels from videos
        channels_map = {}
        for video in response['items']:
            channel_id = video['snippet']['channelId']
            
            if channel_id not in channels_map:
                channels_map[channel_id] = {
                    'title': video['snippet']['channelTitle'],
                    'video_id': video['id'],
                    'video_title': video['snippet']['title'],
                    'views': int(video['statistics'].get('viewCount', 0))
                }
        
        print(f"      ✅ Found {len(channels_map)} unique channels from {len(response['items'])} trending videos")
        
        # Get channel details (to get custom URL/handle)
        channel_ids = list(channels_map.keys())[:max_channels]
        channels_request = youtube.channels().list(
            part="snippet",
            id=','.join(channel_ids)
        )
        channels_response = channels_request.execute()
        
        discoveries = []
        for channel in channels_response['items']:
            channel_id = channel['id']
            custom_url = channel['snippet'].get('customUrl', '')
            
            # Extract handle from customUrl or use channel_id
            if custom_url:
                handle = custom_url.replace('@', '') if custom_url.startswith('@') else custom_url
            else:
                handle = channel_id
            
            video_id = channels_map[channel_id]['video_id']
            video_title = channels_map[channel_id]['video_title']
            
            discoveries.append(YouTubeDiscovery(
                channel_handle=handle,
                channel_id=channel_id,
                channel_url=f"https://www.youtube.com/@{handle}",
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                source="api_trending"
            ))
            
            print(f"      ✅ @{handle} (from: {video_title[:50]}...)")
        
        print(f"      📊 API Cost: ~101 quota units")
        return discoveries
    
    except HttpError as e:
        print(f"      ❌ YouTube API Error: {e}")
        print(f"      ℹ️  Falling back to seed channels...")
        return get_seed_channels(max_channels)
    
    except Exception as e:
        print(f"      ❌ Error: {e}")
        print(f"      ℹ️  Falling back to seed channels...")
        return get_seed_channels(max_channels)


def push_to_kafka(producer: KafkaProducer, discoveries: List[YouTubeDiscovery]):
    """Push discoveries to Kafka"""
    print(f"\n   📤 Pushing {len(discoveries)} discoveries to Kafka...")
    
    for d in discoveries:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "discovery",
            "platform": "youtube",  # ← IMPORTANT!
            "username": d.channel_handle,
            "channel_id": d.channel_id,
            "url": d.channel_url,
            "metadata": {
                "source": d.source,
                "discovery_video": d.video_url
            }
        }
        
        producer.send(
            DISCOVERY_TOPIC,
            value=event
        )
        
        print(f"      ✅ Pushed: @{d.channel_handle}")
    
    producer.flush()
    print(f"   ✅ All {len(discoveries)} discoveries pushed")


def run_discovery_round(producer, api_key: str, max_channels: int, region: str, dry_run: bool = False):
    """Run one discovery round using API"""
    try:
        discoveries = discover_trending_channels_api(api_key, max_channels, region)
        
        if not dry_run and discoveries:
            push_to_kafka(producer, discoveries)
        elif dry_run:
            print(f"\n   ℹ️  DRY RUN - Not pushing to Kafka")
        
        print(f"\n✅ Round completed")
        print(f"📊 Discovered {len(discoveries)} channels")
        
    except Exception as e:
        print(f"\n❌ Discovery round failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="YouTube Discovery (API-based, no Selenium)")
    parser.add_argument("mode", nargs="?", default="once", choices=["once", "daemon"], help="Run mode")
    parser.add_argument("--max-channels", type=int, default=10, help="Max channels to discover")
    parser.add_argument("--interval", type=int, default=21600, help="Interval between rounds (seconds, default 6h)")
    parser.add_argument("--region", default=DEFAULT_REGION, help="YouTube region code (VN, US, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="Don't push to Kafka (test mode)")
    parser.add_argument("--kafka-broker", default=KAFKA_BROKER, help="Kafka broker")
    parser.add_argument("--api-key", default=YOUTUBE_API_KEY, help="YouTube API key")
    args = parser.parse_args()
    
    # Validate API key
    if not args.api_key:
        print("\n❌ ERROR: YOUTUBE_API_KEY not set!")
        print("   Set via environment variable or --api-key argument")
        print("   Example: export YOUTUBE_API_KEY='your_api_key'")
        print("\n   Will use seed channels as fallback...")
    
    print(f"\n{'='*60}")
    print(f"🎬 YouTube Discovery (API-based, NO Selenium)")
    if args.api_key:
        print(f"   API Key: {args.api_key[:20]}...")
    else:
        print(f"   API Key: Not set (using seed channels)")
    print(f"   Region: {args.region}")
    print(f"   Max channels: {args.max_channels}")
    if args.mode == "daemon":
        print(f"   Interval: {args.interval}s ({args.interval/3600:.1f}h)")
    print(f"   Kafka: {args.kafka_broker} → {DISCOVERY_TOPIC}")
    print(f"   Dry run: {args.dry_run}")
    print(f"{'='*60}\n")
    
    # Setup Kafka producer
    producer = None
    if not args.dry_run:
        producer = KafkaProducer(
            bootstrap_servers=args.kafka_broker,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        print(f"✅ Kafka producer ready\n")
    
    if args.mode == "once":
        run_discovery_round(producer, args.api_key, args.max_channels, args.region, args.dry_run)
    else:
        # Daemon mode
        round_num = 0
        while True:
            round_num += 1
            print(f"\n{'━'*60}")
            print(f"🔄 ROUND {round_num} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'━'*60}")
            
            run_discovery_round(producer, args.api_key, args.max_channels, args.region, args.dry_run)
            
            print(f"\n⏳ Sleeping {args.interval}s...")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

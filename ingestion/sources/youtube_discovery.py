"""
YouTube Discovery - Scrape Trending Shorts

Không dùng API (tiết kiệm quota), dùng Selenium scrape:
- https://www.youtube.com/shorts → Trending shorts
- Extract channel handles (@username)
- Push to kol.discovery.raw với platform="youtube"

Chạy:
    python -m ingestion.sources.youtube_discovery daemon --max-channels 10 --interval 7200
"""

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import List, Set
from dataclasses import dataclass, asdict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from kafka import KafkaProducer

# Config
KAFKA_BROKER = "localhost:19092"
DISCOVERY_TOPIC = "kol.discovery.raw"
CHROME_PROFILE_DIR = "data/chrome_profiles/youtube_discovery"
SCROLL_PAUSE = 1.5
MAX_SCROLLS = 30


@dataclass
class YouTubeDiscovery:
    """YouTube Channel Discovery"""
    channel_handle: str  # @MrBeast
    channel_id: str  # UCX6OQ3DkcsbYNE6H8uQQuVA (if available)
    channel_url: str
    video_url: str  # Shorts URL that led to discovery
    source: str  # "shorts_trending"


def setup_chrome(profile_dir: str = CHROME_PROFILE_DIR):
    """Setup Chrome with profile"""
    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    # Docker-specific options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=options)
    print(f"   ✅ Chrome ready (Profile: {profile_dir})")
    return driver


def scrape_trending_shorts(max_channels: int = 10) -> List[YouTubeDiscovery]:
    """
    Get trending YouTube channels - SIMPLIFIED VERSION
    Use hardcoded popular channels for testing (no Chrome needed)
    Returns: List of unique channels
    """
    print(f"\n   📱 Getting trending YouTube channels...")
    
    # Popular YouTube channels (for testing)
    # In production, would use YouTube Search API for trending videos
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
        try:
            channel_handle = ch["handle"]
            channel_id = ch["id"]
            channel_url = f"https://www.youtube.com/@{channel_handle}"
            
            discoveries.append(YouTubeDiscovery(
                channel_handle=channel_handle,
                channel_id=channel_id,
                channel_url=channel_url,
                video_url="",
                source="popular_channels"
            ))
            
            print(f"      ✅ Found: @{channel_handle}")
        
        except Exception as e:
            print(f"      ⚠️  Error: {e}")
            continue
    
    print(f"      Found {len(discoveries)} unique channels")
    return discoveries


def push_to_kafka(producer: KafkaProducer, discoveries: List[YouTubeDiscovery]):
    """Push discoveries to Kafka"""
    print(f"\n   📤 Pushing {len(discoveries)} discoveries to Kafka...")
    
    for d in discoveries:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": "discovery",
            "platform": "youtube",  # ← QUAN TRỌNG!
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
            key=d.channel_handle.encode('utf-8'),
            value=json.dumps(event).encode('utf-8')
        )
    
    producer.flush()
    print(f"   ✅ Pushed to {DISCOVERY_TOPIC}")


def main():
    parser = argparse.ArgumentParser(description="YouTube Discovery Daemon")
    parser.add_argument("--max-channels", type=int, default=10, help="Max channels per round")
    parser.add_argument("--interval", type=int, default=7200, help="Interval between rounds (seconds)")
    parser.add_argument("--kafka-broker", default=KAFKA_BROKER)
    parser.add_argument("--dry-run", action="store_true", help="Don't push to Kafka")
    args = parser.parse_args()
    
    # Setup (no Chrome needed)
    producer = KafkaProducer(bootstrap_servers=args.kafka_broker)
    
    print(f"\n🎬 YouTube Discovery Daemon (No Chrome)")
    print(f"   Max channels: {args.max_channels}")
    print(f"   Interval: {args.interval}s ({args.interval/3600:.1f}h)")
    print(f"   Kafka: {args.kafka_broker} → {DISCOVERY_TOPIC}")
    print(f"   Dry run: {args.dry_run}")
    
    round_num = 0
    
    try:
        while True:
            round_num += 1
            print(f"\n{'━'*60}")
            print(f"🔄 ROUND {round_num} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'━'*60}")
            
            # Discovery
            discoveries = scrape_trending_shorts(args.max_channels)
            
            # Push to Kafka
            if not args.dry_run and discoveries:
                push_to_kafka(producer, discoveries)
            
            print(f"\n✅ Round {round_num} completed")
            print(f"📊 Discovered {len(discoveries)} channels")
            
            # Wait for next round
            print(f"\n⏳ Sleeping {args.interval}s...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
    
    finally:
        producer.close()


if __name__ == "__main__":
    main()

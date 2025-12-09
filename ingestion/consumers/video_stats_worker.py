"""
Video Stats Worker

Lắng nghe kol.discovery.raw → Lấy profile + video stats → Push kol.videos.raw

Flow mới (song song):
- Scraper discovery username → push kol.discovery.raw
- Video Worker lắng nghe discovery.raw → lấy profile + video list + stats
- Comment Worker lắng nghe discovery.raw → lấy comments
- Product Worker lắng nghe discovery.raw → lấy products

Chạy:
    python -m ingestion.consumers.video_stats_worker
"""

import argparse
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from ingestion.consumers.base import BaseConsumer
from ingestion.config import (
    KAFKA_TOPICS,
    CONSUMER_GROUPS,
    MAX_VIDEOS_PER_KOL,
    SCROLL_PAUSE,
)

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class VideoStatsWorker(BaseConsumer):
    """
    Lấy profile + video stats từ username
    
    Input: kol.discovery.raw (username)
    Output: kol.videos.raw (video stats) + kol.profiles.raw (profile)
    """
    
    def __init__(self, max_videos: int = MAX_VIDEOS_PER_KOL, **kwargs):
        super().__init__(**kwargs)
        self.max_videos = max_videos
    
    def get_worker_name(self) -> str:
        return "video"
    
    def get_consumer_group(self) -> str:
        return CONSUMER_GROUPS.get("video_stats_worker", "kol-video-stats-worker")
    
    def get_input_topic(self) -> str:
        return KAFKA_TOPICS["discovery"]
    
    def get_output_topic(self) -> str:
        return KAFKA_TOPICS["videos"]
    
    def process_message(self, message: dict) -> List[dict]:
        """
        Lấy profile + video stats từ username
        
        Args:
            message: Discovery message với username
            
        Returns:
            List of video stats dicts
        """
        username = message.get("username")
        if not username:
            return []
        
        # Check if this is a refresh or new discovery
        event_type = message.get("event_type", "discovery")
        if event_type == "refresh":
            print(f"\n🔄 Refreshing @{username}")
        else:
            print(f"\n🆕 Processing @{username}")
        
        results = []
        
        # 1. Scrape profile và push lên profiles topic
        profile = self._scrape_profile(username)
        if profile:
            # Push profile to kol.profiles.raw
            self._push_profile(profile)
            print(f"   ✅ Profile: {profile.get('followers_raw', 'N/A')} followers")
        
        # 2. Get video list
        video_list = self._scrape_video_list(username)
        print(f"   📹 Found {len(video_list)} videos")
        
        # 3. Scrape stats for each video
        for video_url, caption in video_list:
            if not self.running:
                break
            
            video = self._scrape_video_stats(video_url, username, caption)
            if video:
                results.append(video)
            
            time.sleep(0.5)
        
        print(f"   ✅ Scraped {len(results)} video stats")
        return results
    
    def _scrape_profile(self, username: str) -> Optional[dict]:
        """Scrape profile data"""
        url = f"https://www.tiktok.com/@{username}"
        
        if not self._safe_get(url):
            return None
        
        try:
            profile = {
                "event_id": str(uuid.uuid4()),
                "event_time": datetime.now(timezone.utc).isoformat(),
                "event_type": "profile",
                "platform": "tiktok",
                "username": username,
                "profile_url": url,
            }
            
            # Followers
            try:
                el = self.driver.find_element(By.XPATH, "//strong[contains(@data-e2e,'followers')]")
                profile["followers_raw"] = el.text.strip()
            except:
                pass
            
            # Following
            try:
                el = self.driver.find_element(By.XPATH, "//strong[contains(@data-e2e,'following')]")
                profile["following_raw"] = el.text.strip()
            except:
                pass
            
            # Likes
            try:
                el = self.driver.find_element(By.XPATH, "//strong[contains(@data-e2e,'likes')]")
                profile["likes_raw"] = el.text.strip()
            except:
                pass
            
            # Bio
            try:
                el = self.driver.find_element(By.XPATH, "//h2[contains(@data-e2e,'user-bio')]")
                profile["bio"] = el.text.strip()
            except:
                pass
            
            return profile
        
        except Exception as e:
            self._log_error(f"Profile error @{username}: {e}")
            return None
    
    def _push_profile(self, profile: dict):
        """Push profile lên kol.profiles.raw topic"""
        if self.producer and profile:
            try:
                topic = KAFKA_TOPICS["profiles"]
                key = profile.get("username", "unknown")
                self.producer.send(topic, key=key, value=profile)
                self.stats["profiles_produced"] = self.stats.get("profiles_produced", 0) + 1
            except Exception as e:
                self._log_error(f"Failed to push profile: {e}")
    
    def _scrape_video_list(self, username: str) -> List[Tuple[str, Optional[str]]]:
        """Scroll profile và lấy video URLs"""
        url = f"https://www.tiktok.com/@{username}"
        
        if not self._safe_get(url):
            return []
        
        video_data: Dict[str, Optional[str]] = {}
        
        for scroll in range(40):
            if not self.running:
                break
            
            time.sleep(SCROLL_PAUSE)
            
            try:
                anchors = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/video/')]")
                
                for a in anchors:
                    try:
                        href = a.get_attribute("href") or ""
                        if "/video/" not in href:
                            continue
                        
                        if href not in video_data:
                            caption = None
                            for attr in ["title", "aria-label"]:
                                val = a.get_attribute(attr)
                                if val:
                                    caption = val.strip()
                                    break
                            video_data[href] = caption
                    except:
                        continue
                
                if len(video_data) >= self.max_videos:
                    break
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            except:
                break
        
        return [(url, caption) for url, caption in list(video_data.items())[:self.max_videos]]
    
    def _scrape_video_stats(self, video_url: str, username: str, caption: Optional[str]) -> Optional[dict]:
        """Scrape video stats"""
        video_id = self._parse_video_id(video_url)
        if not video_id:
            return None
        
        try:
            self.driver.get(video_url)
            
            wait = WebDriverWait(self.driver, 15)
            try:
                wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//*[contains(@data-e2e,'like-count') or contains(@data-e2e,'browse-video')]"
                )))
            except TimeoutException:
                return None
            
            time.sleep(1.5)
            self._close_popup()
            
            video = {
                "event_id": str(uuid.uuid4()),
                "event_time": datetime.now(timezone.utc).isoformat(),
                "event_type": "video",
                "platform": "tiktok",
                "video_id": video_id,
                "video_url": video_url,
                "username": username,
                "caption": caption[:500] if caption else None,
            }
            
            # Like count
            try:
                el = self.driver.find_element(By.XPATH, "//*[contains(@data-e2e,'like-count')]")
                video["like_count_raw"] = el.text.strip()
                video["like_count"] = self._normalize_count(video["like_count_raw"])
            except:
                pass
            
            # Comment count
            try:
                el = self.driver.find_element(By.XPATH, "//*[contains(@data-e2e,'comment-count')]")
                video["comment_count_raw"] = el.text.strip()
                video["comment_count"] = self._normalize_count(video["comment_count_raw"])
            except:
                pass
            
            # Share count
            try:
                el = self.driver.find_element(By.XPATH, "//*[contains(@data-e2e,'share-count')]")
                video["share_count_raw"] = el.text.strip()
                video["share_count"] = self._normalize_count(video["share_count_raw"])
            except:
                pass
            
            # View count
            for xpath in [
                "//*[contains(@data-e2e,'video-views')]",
                "//*[contains(@data-e2e,'browse-video-count')]",
                "//*[contains(@data-e2e,'play-count')]",
            ]:
                try:
                    el = self.driver.find_element(By.XPATH, xpath)
                    video["view_count_raw"] = el.text.strip()
                    video["view_count"] = self._normalize_count(video["view_count_raw"])
                    break
                except:
                    pass
            
            return video
        
        except Exception as e:
            self._log_error(f"Video error {video_url}: {e}")
            return None
    
    def _parse_video_id(self, url: str) -> Optional[str]:
        """Extract video ID từ URL"""
        m = re.search(r"/video/(\d+)", url)
        return m.group(1) if m else None
    
    def _normalize_count(self, text: Optional[str]) -> Optional[int]:
        """Convert '1.2K' → 1200"""
        if not text:
            return None
        try:
            t = text.strip().lower().replace(",", "").replace(" ", "")
            factor = 1
            if t.endswith("k"):
                factor = 1_000
                t = t[:-1]
            elif t.endswith("m"):
                factor = 1_000_000
                t = t[:-1]
            elif t.endswith("b"):
                factor = 1_000_000_000
                t = t[:-1]
            return int(float(t) * factor)
        except:
            return None


def main():
    parser = argparse.ArgumentParser(description="Video Stats Worker")
    parser.add_argument("--dry-run", action="store_true", help="Run without Kafka")
    parser.add_argument("--no-selenium", action="store_true", help="Disable Selenium")
    parser.add_argument("--max-videos", type=int, default=20)
    parser.add_argument("--start-delay", type=int, default=0, 
                        help="Delay in seconds before starting (wait for Discovery)")
    args = parser.parse_args()
    
    # Delay if specified (để đợi Discovery push messages trước)
    if args.start_delay > 0:
        print(f"\n⏳ Waiting {args.start_delay}s for Discovery to push messages...")
        print(f"   (This ensures we process NEW messages, not old ones)")
        import time
        for i in range(args.start_delay, 0, -30):
            print(f"   ⏰ {i}s remaining...")
            time.sleep(min(30, i))
        print("   ✅ Starting now!\n")
    
    worker = VideoStatsWorker(
        use_selenium=not args.no_selenium,
        dry_run=args.dry_run,
        max_videos=args.max_videos,
    )
    worker.run()


if __name__ == "__main__":
    main()

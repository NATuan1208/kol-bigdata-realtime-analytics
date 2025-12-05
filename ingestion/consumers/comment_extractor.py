"""
Comment Extractor Worker

Flow mới (song song):
- Lắng nghe kol.discovery.raw (username)
- Tự scroll video list của username
- Lấy comments từ mỗi video
- Push kol.comments.raw

Chạy:
    python -m ingestion.consumers.comment_extractor
    
Hoặc với dry-run (không cần Kafka):
    python -m ingestion.consumers.comment_extractor --dry-run
"""

import argparse
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

from ingestion.consumers.base import BaseConsumer
from ingestion.config import (
    KAFKA_TOPICS,
    CONSUMER_GROUPS,
    MAX_COMMENTS_PER_VIDEO,
    MAX_VIDEOS_PER_KOL,
    SCROLL_PAUSE,
)

from selenium.webdriver.common.by import By


class CommentExtractor(BaseConsumer):
    """
    Extract comments từ TikTok videos
    
    Input: kol.discovery.raw (username)
    Output: kol.comments.raw (video_id, comment_text)
    """
    
    def __init__(
        self, 
        max_comments: int = MAX_COMMENTS_PER_VIDEO,
        max_videos: int = 20,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.max_comments = max_comments
        self.max_videos = max_videos
    
    def get_worker_name(self) -> str:
        return "comment"
    
    def get_consumer_group(self) -> str:
        return CONSUMER_GROUPS["comment_extractor"]
    
    def get_input_topic(self) -> str:
        # Lắng nghe discovery.raw thay vì videos.raw
        return KAFKA_TOPICS["discovery"]
    
    def get_output_topic(self) -> str:
        return KAFKA_TOPICS["comments"]
    
    def process_message(self, message: dict) -> List[dict]:
        """
        Nhận username từ discovery → scroll video list → lấy comments
        
        Args:
            message: Discovery message với username
            
        Returns:
            List of comment dicts
        """
        username = message.get("username")
        if not username:
            return []
        
        print(f"\n💬 Comment extraction for @{username}")
        
        # 1. Scroll video list của username
        video_list = self._scrape_video_list(username)
        print(f"   📹 Found {len(video_list)} videos")
        
        # 2. Lấy comments từ mỗi video
        all_comments = []
        for i, (video_url, _) in enumerate(video_list):
            if not self.running:
                break
            
            video_id = self._parse_video_id(video_url)
            if not video_id:
                continue
            
            print(f"   [{i+1}/{len(video_list)}] Video {video_id}...", end="")
            
            comments = self._scrape_comments(video_url, video_id, username)
            all_comments.extend(comments)
            
            if comments:
                print(f" ✅ {len(comments)} comments")
            else:
                print(f" ⏭️ 0")
            
            time.sleep(0.5)
        
        print(f"   ✅ Total: {len(all_comments)} comments from {len(video_list)} videos")
        return all_comments
    
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
    
    def _scrape_comments(self, video_url: str, video_id: str, username: str) -> List[dict]:
        """Scrape comments từ video page"""
        if not self._safe_get(video_url):
            return []
        
        time.sleep(2)  # Wait for page load
        
        comments = []
        seen_texts: Set[str] = set()
        
        max_scrolls = min(120, max(50, self.max_comments // 2))
        no_new_count = 0
        
        for scroll in range(max_scrolls):
            if not self.running or len(comments) >= self.max_comments:
                break
            
            prev_count = len(comments)
            
            # Collect visible comments
            try:
                items = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    '[class*="CommentItem"], [class*="DivCommentObjectWrapper"]'
                )
                
                for item in items:
                    if len(comments) >= self.max_comments:
                        break
                    
                    try:
                        raw_text = item.text.strip()
                        if not raw_text or len(raw_text) < 3:
                            continue
                        
                        lines = raw_text.split('\n')
                        if len(lines) >= 2:
                            text = lines[1].strip()
                        else:
                            continue
                        
                        # Skip metadata
                        if len(text) < 2:
                            continue
                        if text.lower() in ['reply', 'like', 'share', 'see more', 'view replies', 'xem thêm']:
                            continue
                        if re.match(r'^\d+[hmd]?\s*(ago)?$', text.lower()):
                            continue
                        if re.match(r'^\d+-\d+$', text):
                            continue
                        if re.match(r'^\d+$', text):
                            continue
                        
                        if text not in seen_texts:
                            seen_texts.add(text)
                            comments.append({
                                "event_id": str(uuid.uuid4()),
                                "event_time": datetime.now(timezone.utc).isoformat(),
                                "event_type": "comment",
                                "platform": "tiktok",
                                "video_id": video_id,
                                "video_url": video_url,
                                "username": username,
                                "comment_text": text[:1000],
                            })
                    except:
                        continue
            except:
                pass
            
            # Check progress
            new_count = len(comments) - prev_count
            if new_count == 0:
                no_new_count += 1
                if no_new_count >= 10:
                    break
                delay = 0.5
            elif new_count <= 2:
                no_new_count = 0
                delay = 0.35
            else:
                no_new_count = 0
                delay = 0.2
            
            # Scroll
            try:
                self.driver.execute_script('window.scrollBy(0, 300);')
                time.sleep(delay)
            except:
                break
        
        return comments
    
    def _parse_video_id(self, url: str) -> Optional[str]:
        """Extract video ID từ URL"""
        m = re.search(r"/video/(\d+)", url)
        return m.group(1) if m else None


def main():
    parser = argparse.ArgumentParser(description="Comment Extractor Worker")
    parser.add_argument("--dry-run", action="store_true", help="Run without Kafka")
    parser.add_argument("--no-selenium", action="store_true", help="Disable Selenium")
    parser.add_argument("--max-comments", type=int, default=MAX_COMMENTS_PER_VIDEO)
    parser.add_argument("--max-videos", type=int, default=20)
    parser.add_argument("--start-delay", type=int, default=0,
                        help="Delay in seconds before starting (wait for Discovery)")
    args = parser.parse_args()
    
    # Delay if specified
    if args.start_delay > 0:
        print(f"\n⏳ Waiting {args.start_delay}s for Discovery to push messages...")
        import time
        for i in range(args.start_delay, 0, -30):
            print(f"   ⏰ {i}s remaining...")
            time.sleep(min(30, i))
        print("   ✅ Starting now!\n")
    
    consumer = CommentExtractor(
        use_selenium=not args.no_selenium,
        dry_run=args.dry_run,
        max_comments=args.max_comments,
        max_videos=args.max_videos,
    )
    consumer.run()


if __name__ == "__main__":
    main()

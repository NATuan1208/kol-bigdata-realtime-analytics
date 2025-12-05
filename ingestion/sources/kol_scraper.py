"""
KOL SCRAPER – TikTok (Unified Scraper)

Kiến trúc chuẩn Enterprise:
--------------------------------
Scraper CHỈ làm 1 việc: Scrape raw data và push lên Kafka
KHÔNG xử lý logic, KHÔNG tính toán - để Spark làm

Flow:
--------------------------------
┌─────────────────────────────────────────────────────────────────┐
│                         KOL SCRAPER                             │
│                                                                 │
│   Mode 1: DISCOVERY                                             │
│   ─────────────────                                             │
│   Search/FYP → Tìm username mới → Push kol.discovery.raw       │
│                                                                 │
│   Mode 2: PROFILE                                               │
│   ───────────────                                               │
│   Username → Scrape profile → Push kol.profiles.raw            │
│                                                                 │
│   Mode 3: VIDEOS                                                │
│   ─────────────                                                 │
│   Username → Scrape N videos + stats → Push kol.videos.raw     │
│                                                                 │
│   Mode 4: COMMENTS                                              │
│   ────────────────                                              │
│   Video URL → Scrape comments → Push kol.comments.raw          │
│                                                                 │
│   Mode 5: PRODUCTS                                              │
│   ────────────────                                              │
│   Username → Check shop + products → Push kol.products.raw     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Kafka Topics:
--------------------------------
kol.discovery.raw   - Raw discovery (username, video_url, source)
kol.profiles.raw    - Raw profiles (followers, bio, verified, etc.)
kol.videos.raw      - Raw video stats (views, likes, comments, shares)
kol.comments.raw    - Raw comments (text, author, timestamp)
kol.products.raw    - Raw products (name, price, sold_count)

Usage:
--------------------------------
# Discovery mode - tìm KOL mới
python kol_scraper.py discovery --mode single

# Profile mode - scrape profile từ list usernames
python kol_scraper.py profile --usernames user1,user2,user3

# Videos mode - scrape videos từ username
python kol_scraper.py videos --username mixigaming --max-videos 50

# Full pipeline - discovery + profile + videos
python kol_scraper.py full --mode single
"""

import argparse
import json
import random
import re
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Import shared utils - support both direct run and module run
try:
    from scraper_utils import (
        # Config
        DEFAULT_KAFKA_BROKER,
        OUTPUT_DIR,
        SCROLL_PAUSE,
        
        # Helpers
        log_error,
        load_json,
        save_json,
        normalize_count,
        extract_video_id,
        extract_username_from_url,
        is_interrupted,
        setup_signal_handler,
    
        # WebDriver
        create_driver,
        safe_get,
        close_popup,
        text_or_none,
        safe_get_attribute,
    
        # Kafka
        KafkaStreamer,
        KAFKA_AVAILABLE,
    )
except ImportError:
    from ingestion.sources.scraper_utils import (
        # Config
        DEFAULT_KAFKA_BROKER,
        OUTPUT_DIR,
        SCROLL_PAUSE,
        
        # Helpers
        log_error,
        load_json,
        save_json,
        normalize_count,
        extract_video_id,
        extract_username_from_url,
        is_interrupted,
        setup_signal_handler,
    
        # WebDriver
        create_driver,
        safe_get,
        close_popup,
        text_or_none,
        safe_get_attribute,
    
        # Kafka
        KafkaStreamer,
        KAFKA_AVAILABLE,
    )


# ===================== CONFIG =====================

# Kafka topics - Raw data only
KAFKA_TOPICS = {
    "discovery": "kol.discovery.raw",
    "profiles": "kol.profiles.raw",
    "videos": "kol.videos.raw",
    "comments": "kol.comments.raw",
    "products": "kol.products.raw",
    "events": "kol.scraper.events",
}

# Scraping settings
MAX_VIDEOS_PER_KOL = 100
MAX_COMMENTS_PER_VIDEO = 50
MAX_SEARCH_SCROLLS = 10
MAX_FYP_SCROLLS = 15
KEYWORDS_PER_ROUND = 6  # Tăng từ 3 lên 6 để cover nhiều niche hơn

# Product metrics - Proxy since TikTok doesn't expose buy_count/click_count
DEFAULT_CTR = 0.0387  # ~3.87% avg CTR for TikTok Shop based on industry data

# Keywords theo niche
NICHE_KEYWORDS: Dict[str, List[str]] = {
    "beauty": [
        "review mỹ phẩm", "skincare routine", "makeup tutorial",
        "son môi", "kem chống nắng", "serum vitamin c",
    ],
    "fashion": [
        "outfit của ngày", "mix đồ", "thời trang công sở",
        "streetwear vietnam", "unboxing shopee", "haul shopee",
    ],
    "tech": [
        "đánh giá điện thoại", "review laptop", "phụ kiện công nghệ",
        "tips iphone", "android hay ios", "unbox công nghệ",
    ],
    "food": [
        "review đồ ăn", "ăn gì hôm nay", "food tour",
        "nấu ăn tại nhà", "mukbang vietnam", "quán ngon sài gòn",
    ],
    "lifestyle": [
        "một ngày của tui", "room tour", "sống tối giản",
        "vlog cuộc sống", "self improvement", "daily routine",
    ],
    "gaming": [
        "gameplay vietnam", "liên quân mobile", "free fire vietnam",
        "review game", "esports vietnam", "genshin impact",
    ],
}

# Paths
CHECKPOINT_PATH = OUTPUT_DIR / "scraper_checkpoint.json"
ERROR_LOG_PATH = OUTPUT_DIR / "scraper_errors.log"


# ===================== HELPER FUNCTIONS =====================

def now_iso() -> str:
    """Get current time in ISO format with timezone"""
    return datetime.now(timezone.utc).isoformat()


def parse_video_id(url: str) -> Optional[str]:
    """Extract video ID từ URL"""
    m = re.search(r"/video/(\d+)", url)
    return m.group(1) if m else None


# ===================== DATA MODELS (Raw Only) =====================

@dataclass
class RawDiscovery:
    """Raw discovery data - NO processing"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_time: str = field(default_factory=now_iso)
    event_type: str = "discovery"
    platform: str = "tiktok"
    
    username: str = ""
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    caption: Optional[str] = None
    source: str = ""  # "search:keyword" or "trending"
    keyword: Optional[str] = None
    niche_hint: Optional[str] = None


@dataclass
class RawProfile:
    """Raw profile data - NO processing"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_time: str = field(default_factory=now_iso)
    event_type: str = "profile"
    platform: str = "tiktok"
    
    username: str = ""
    nickname: Optional[str] = None
    followers_raw: Optional[str] = None      # Raw text "1.2M"
    following_raw: Optional[str] = None
    likes_raw: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    verified: bool = False
    profile_url: str = ""


@dataclass 
class RawVideo:
    """Raw video data - NO processing"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_time: str = field(default_factory=now_iso)
    event_type: str = "video"
    platform: str = "tiktok"
    
    video_id: str = ""
    video_url: str = ""
    username: str = ""
    caption: Optional[str] = None
    
    # Raw stats (text như "1.2K", "3.4M")
    view_count_raw: Optional[str] = None
    like_count_raw: Optional[str] = None
    comment_count_raw: Optional[str] = None
    share_count_raw: Optional[str] = None
    
    # Parsed stats (để Spark không phải parse lại)
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None


@dataclass
class RawComment:
    """Raw comment data - For spam detection training (phoBERT)"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_time: str = field(default_factory=now_iso)
    event_type: str = "comment"
    platform: str = "tiktok"
    
    video_id: str = ""
    video_url: str = ""
    username: str = ""  # Video owner (for context)
    
    # Only need text for spam detection
    comment_text: str = ""


@dataclass
class RawProduct:
    """Raw product data from TikTok Shop - Full details"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_time: str = field(default_factory=now_iso)
    event_type: str = "product"
    platform: str = "tiktok"
    
    # Video context
    username: str = ""
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    
    # Video stats (when scraping from video)
    video_views: Optional[int] = None
    video_likes: Optional[int] = None
    video_comments: Optional[int] = None
    video_shares: Optional[int] = None
    
    # Shop info
    has_shop: bool = False
    
    # Product details
    product_id: Optional[str] = None
    product_title: Optional[str] = None
    seller_id: Optional[str] = None
    price: Optional[int] = None
    currency: str = "VND"
    product_url: Optional[str] = None
    keyword: Optional[str] = None  # Anchor text in video
    
    # Sales data
    sold_count: Optional[int] = None
    sold_count_raw: Optional[str] = None
    sold_delta: Optional[int] = None  # Change since last scrape
    
    # Calculated features (proxy metrics since TikTok doesn't expose buy_count/click_count)
    engagement_total: Optional[int] = None      # likes + comments + shares
    engagement_rate: Optional[float] = None     # engagement_total / views
    est_clicks: Optional[int] = None            # views * DEFAULT_CTR (proxy for add-to-cart clicks)
    est_ctr: Optional[float] = None             # DEFAULT_CTR = 0.03-0.04 based on industry avg


# ===================== SCRAPER CLASS =====================

class KOLScraper:
    """Unified TikTok Scraper"""
    
    def __init__(
        self,
        kafka_broker: str = DEFAULT_KAFKA_BROKER,
        dry_run: bool = False,
        headless: bool = False,
        use_profile: bool = True,
    ):
        self.kafka_broker = kafka_broker
        self.dry_run = dry_run
        self.headless = headless
        self.use_profile = use_profile
        
        self.driver = None
        self.kafka = None
        
        # Stats
        self.stats = {
            "discovery": 0,
            "profiles": 0,
            "videos": 0,
            "comments": 0,
            "products": 0,
            "errors": 0,
        }
        
        # Checkpoint
        checkpoint = load_json(CHECKPOINT_PATH, {
            "seen_usernames": [],
            "seen_videos": [],
            "round": 0,
        })
        self.seen_usernames: Set[str] = set(checkpoint.get("seen_usernames", []))
        self.seen_videos: Set[str] = set(checkpoint.get("seen_videos", []))
        self.round_number = checkpoint.get("round", 0)
    
    def start(self):
        """Initialize browser and Kafka"""
        print("\n" + "="*60)
        print("🚀 KOL SCRAPER - TikTok")
        print("="*60)
        print(f"Kafka: {'DRY-RUN' if self.dry_run else self.kafka_broker}")
        print(f"Headless: {self.headless}")
        print("="*60)
        
        # Kafka producer
        self.kafka = KafkaStreamer(
            broker=self.kafka_broker,
            dry_run=self.dry_run or not KAFKA_AVAILABLE,
        )
        
        # WebDriver - use profile for session persistence
        print("\n🌐 Starting browser...")
        self.driver = create_driver(headless=self.headless, use_profile=self.use_profile)
        
        # Warm up
        print("🔄 Warming up TikTok...")
        safe_get(self.driver, "https://www.tiktok.com/foryou", "warmup")
        print("✅ Ready!\n")
    
    def stop(self):
        """Cleanup"""
        print("\n🔒 Stopping scraper...")
        
        # Save checkpoint - keep last N items
        checkpoint = {
            "seen_usernames": list(self.seen_usernames)[-5000:] if self.seen_usernames else [],
            "seen_videos": list(self.seen_videos)[-10000:] if self.seen_videos else [],
            "round": self.round_number,
        }
            
        save_json(CHECKPOINT_PATH, checkpoint)
        
        # Close connections
        if self.driver:
            self.driver.quit()
        
        if self.kafka:
            self.kafka.close()
        
        # Print stats
        print("\n" + "="*60)
        print("📊 SCRAPER STATS")
        print("="*60)
        for key, value in self.stats.items():
            print(f"   {key}: {value}")
        print("="*60)
    
    # ==================== DISCOVERY ====================
    
    def discover_from_search(self, keyword: str) -> List[RawDiscovery]:
        """Search TikTok và tìm creators mới"""
        print(f"\n   🔍 Search: '{keyword}'")
        
        encoded = quote(keyword)
        url = f"https://www.tiktok.com/search/video?q={encoded}"
        
        if not safe_get(self.driver, url, f"search '{keyword}'", wait_for_content=True):
            return []
        
        # Extra wait for search results
        time.sleep(2)
        
        discoveries = []
        seen_videos: Set[str] = set()
        
        # Determine niche from keyword
        niche_hint = None
        for niche, keywords in NICHE_KEYWORDS.items():
            if keyword in keywords:
                niche_hint = niche
                break
        
        for scroll in range(MAX_SEARCH_SCROLLS):
            if is_interrupted():
                break
            
            time.sleep(SCROLL_PAUSE)
            
            try:
                # Method 1: Try XPATH first (most specific)
                links = self.driver.find_elements(
                    By.XPATH, 
                    "//a[contains(@href, '/@') and contains(@href, '/video/')]"
                )
                
                # Method 2: If no results, try CSS selector
                if not links:
                    links = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        'a[href*="/@"][href*="/video/"]'
                    )
                
                # Method 3: Fallback - get all user links and filter
                if not links:
                    all_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/@"]')
                    links = [l for l in all_links if '/video/' in (l.get_attribute('href') or '')]
                
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "/video/" not in href:
                        continue
                    
                    video_id = extract_video_id(href)
                    if not video_id or video_id in seen_videos:
                        continue
                    
                    seen_videos.add(video_id)
                    
                    username = extract_username_from_url(href)
                    if not username or username.lower() in self.seen_usernames:
                        continue
                    
                    self.seen_usernames.add(username.lower())
                    
                    caption = None
                    try:
                        caption = link.get_attribute("title") or link.get_attribute("aria-label")
                    except:
                        pass
                    
                    discoveries.append(RawDiscovery(
                        username=username,
                        video_id=video_id,
                        video_url=href,
                        caption=caption[:500] if caption else None,
                        source=f"search:{keyword}",
                        keyword=keyword,
                        niche_hint=niche_hint,
                    ))
            
            except Exception as e:
                log_error(f"Search scroll error: {e}", ERROR_LOG_PATH)
            
            # Scroll
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except:
                break
        
        print(f"      Found {len(discoveries)} new creators")
        return discoveries
    
    def discover_from_fyp(self) -> List[RawDiscovery]:
        """Scroll FYP và tìm trending creators"""
        print(f"\n   📱 Scrolling FYP...")
        
        if not safe_get(self.driver, "https://www.tiktok.com/foryou", "FYP"):
            return []
        
        discoveries = []
        seen_videos: Set[str] = set()
        
        for scroll in range(MAX_FYP_SCROLLS):
            if is_interrupted():
                break
            
            time.sleep(SCROLL_PAUSE + 1)
            
            try:
                links = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href, '/@') and contains(@href, '/video/')]"
                )
                
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "/video/" not in href:
                        continue
                    
                    video_id = extract_video_id(href)
                    if not video_id or video_id in seen_videos:
                        continue
                    
                    seen_videos.add(video_id)
                    
                    username = extract_username_from_url(href)
                    if not username or username.lower() in self.seen_usernames:
                        continue
                    
                    self.seen_usernames.add(username.lower())
                    
                    caption = None
                    try:
                        caption = link.get_attribute("title") or link.get_attribute("aria-label")
                    except:
                        pass
                    
                    discoveries.append(RawDiscovery(
                        username=username,
                        video_id=video_id,
                        video_url=href,
                        caption=caption[:500] if caption else None,
                        source="trending",
                    ))
                    
                    if len(discoveries) >= 20:
                        break
            
            except Exception as e:
                log_error(f"FYP scroll error: {e}", ERROR_LOG_PATH)
            
            if len(discoveries) >= 20:
                break
            
            try:
                self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            except:
                break
        
        print(f"      Found {len(discoveries)} new creators")
        return discoveries
    
    # ==================== PROFILE ====================
    
    def scrape_profile(self, username: str) -> Optional[RawProfile]:
        """Scrape raw profile data"""
        url = f"https://www.tiktok.com/@{username}"
        print(f"   👤 Profile: @{username}")
        
        if not safe_get(self.driver, url, f"@{username}"):
            return None
        
        try:
            profile = RawProfile(
                username=username,
                profile_url=url,
            )
            
            # Nickname
            profile.nickname = text_or_none(
                self.driver, 
                "//h2[contains(@data-e2e,'user-subtitle')]"
            )
            
            # Followers (raw text)
            profile.followers_raw = text_or_none(
                self.driver,
                "//strong[contains(@data-e2e,'followers')]"
            )
            
            # Following
            profile.following_raw = text_or_none(
                self.driver,
                "//strong[contains(@data-e2e,'following')]"
            )
            
            # Likes
            profile.likes_raw = text_or_none(
                self.driver,
                "//strong[contains(@data-e2e,'likes')]"
            )
            
            # Bio
            profile.bio = text_or_none(
                self.driver,
                "//h2[contains(@data-e2e,'user-bio')]"
            )
            
            # Avatar
            try:
                avatar = self.driver.find_element(
                    By.XPATH, 
                    "//img[contains(@data-e2e,'user-avatar')]"
                )
                profile.avatar_url = avatar.get_attribute("src")
            except:
                pass
            
            # Verified
            try:
                self.driver.find_element(By.XPATH, "//*[contains(@data-e2e,'verified')]")
                profile.verified = True
            except:
                profile.verified = False
            
            return profile
        
        except Exception as e:
            log_error(f"Profile error @{username}: {e}", ERROR_LOG_PATH)
            return None
    
    # ==================== VIDEOS ====================
    
    def scrape_video_list(self, username: str, max_videos: int = MAX_VIDEOS_PER_KOL) -> List[Tuple[str, Optional[str]]]:
        """Scroll profile và lấy list video URLs"""
        url = f"https://www.tiktok.com/@{username}"
        print(f"   🎬 Getting video list @{username}")
        
        if not safe_get(self.driver, url, f"@{username}"):
            return []
        
        video_data: Dict[str, Optional[str]] = {}  # url -> caption
        
        for scroll in range(40):
            if is_interrupted():
                break
            
            time.sleep(SCROLL_PAUSE)
            
            try:
                anchors = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/video/')]")
                
                for a in anchors:
                    href = safe_get_attribute(a, "href") or ""
                    if "/video/" not in href:
                        continue
                    
                    if href not in video_data:
                        caption = None
                        for attr in ["title", "aria-label"]:
                            val = safe_get_attribute(a, attr)
                            if val:
                                caption = val.strip()
                                break
                        video_data[href] = caption
                
                if len(video_data) >= max_videos:
                    break
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            except Exception as e:
                break
        
        result = [(url, caption) for url, caption in list(video_data.items())[:max_videos]]
        print(f"      Found {len(result)} videos")
        return result
    
    def scrape_video_stats(self, video_url: str, username: str, caption: Optional[str] = None) -> Optional[RawVideo]:
        """Scrape raw video stats"""
        if is_interrupted():
            return None
        
        video_id = parse_video_id(video_url)
        if not video_id:
            return None
        
        if video_id in self.seen_videos:
            return None
        
        self.seen_videos.add(video_id)
        
        try:
            self.driver.get(video_url)
            
            # Wait for stats
            wait = WebDriverWait(self.driver, 15)
            try:
                wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//*[contains(@data-e2e,'like-count') or contains(@data-e2e,'browse-video')]"
                )))
            except TimeoutException:
                return None
            
            time.sleep(1.5)
            close_popup(self.driver)
            
            video = RawVideo(
                video_id=video_id,
                video_url=video_url,
                username=username,
                caption=caption[:500] if caption else None,
            )
            
            # Like count
            video.like_count_raw = text_or_none(
                self.driver,
                "//*[contains(@data-e2e,'like-count')]"
            )
            video.like_count = normalize_count(video.like_count_raw)
            
            # Comment count
            video.comment_count_raw = text_or_none(
                self.driver,
                "//*[contains(@data-e2e,'comment-count')]"
            )
            video.comment_count = normalize_count(video.comment_count_raw)
            
            # Share count
            video.share_count_raw = text_or_none(
                self.driver,
                "//*[contains(@data-e2e,'share-count')]"
            )
            video.share_count = normalize_count(video.share_count_raw)
            
            # View count (multiple selectors)
            for xpath in [
                "//*[contains(@data-e2e,'video-views')]",
                "//*[contains(@data-e2e,'browse-video-count')]",
                "//*[contains(@data-e2e,'play-count')]",
            ]:
                video.view_count_raw = text_or_none(self.driver, xpath)
                if video.view_count_raw:
                    video.view_count = normalize_count(video.view_count_raw)
                    break
            
            return video
        
        except Exception as e:
            log_error(f"Video error {video_url}: {e}", ERROR_LOG_PATH)
            return None
    
    # ==================== COMMENTS ====================
    
    def scrape_comments(self, video_url: str, username: str, max_comments: int = MAX_COMMENTS_PER_VIDEO) -> List[RawComment]:
        """
        Scrape level-1 comments từ video bằng cách scroll page.
        TikTok yêu cầu login để click vào comment icon, nên ta scroll page thay vì click.
        """
        video_id = parse_video_id(video_url)
        if not video_id:
            return []
        
        print(f"      💬 Comments: {video_id}")
        
        if not safe_get(self.driver, video_url, f"video {video_id}"):
            return []
        
        close_popup(self.driver)
        
        # Scroll xuống phần comments ngay lập tức
        try:
            # Scroll nhanh xuống vùng comments (~2000px)
            self.driver.execute_script('window.scrollTo(0, 2000);')
            time.sleep(0.5)
        except:
            pass
        
        comments = []
        seen_texts: Set[str] = set()
        
        # ========== Scroll page and collect comments ==========
        # TikTok virtualizes DOM, so we collect while scrolling
        
        max_scrolls = min(120, max(50, max_comments // 2))
        no_new_count = 0
        
        for scroll in range(max_scrolls):
            if is_interrupted() or len(comments) >= max_comments:
                break
            
            prev_count = len(comments)
            
            # Collect visible comments
            try:
                # TikTok 2024+: CommentItem or DivCommentObjectWrapper
                items = self.driver.find_elements(By.CSS_SELECTOR, '[class*="CommentItem"], [class*="DivCommentObjectWrapper"]')
                
                for item in items:
                    if len(comments) >= max_comments:
                        break
                    
                    try:
                        raw_text = item.text.strip()
                        if not raw_text or len(raw_text) < 3:
                            continue
                        
                        # Format: "username\ncomment_text\ndate\nReply\nlike_count"
                        lines = raw_text.split('\n')
                        
                        # Comment text is 2nd line (after username)
                        if len(lines) >= 2:
                            text = lines[1].strip()
                        else:
                            continue
                        
                        # Skip metadata lines
                        if len(text) < 2:
                            continue
                        if text.lower() in ['reply', 'like', 'share', 'see more', 'view replies', 'xem thêm']:
                            continue
                        if re.match(r'^\d+[hmd]?\s*(ago)?$', text.lower()):
                            continue
                        if re.match(r'^\d+-\d+$', text):  # Date format like "5-17"
                            continue
                        if re.match(r'^\d+$', text):  # Just numbers
                            continue
                        if text.lower().startswith('view ') and 'repl' in text.lower():
                            continue
                        
                        if text not in seen_texts:
                            seen_texts.add(text)
                            comments.append(RawComment(
                                video_id=video_id,
                                video_url=video_url,
                                username=username,
                                comment_text=text[:1000],
                            ))
                    except:
                        continue
            except:
                pass
            
            # Check progress & adaptive delay
            new_count = len(comments) - prev_count
            if new_count == 0:
                no_new_count += 1
                if no_new_count >= 10:
                    break
                delay = 0.5  # Chờ lâu hơn khi không có comment mới
            elif new_count <= 2:
                no_new_count = 0
                delay = 0.35  # Chậm lại khi ít comment
            else:
                no_new_count = 0
                delay = 0.2  # Nhanh khi nhiều comment
            
            # Scroll page down
            try:
                self.driver.execute_script('window.scrollBy(0, 300);')
                time.sleep(delay)
            except:
                break
        
        if comments:
            print(f" ✅ {len(comments)} comments")
        else:
            print(f" ⏭️ No comments found")
        
        return comments
    
    # ==================== PRODUCTS ====================
    
    def _parse_sold_count(self, sold_text: str) -> Optional[int]:
        """Convert '188.5K' → 188500, '2.0K' → 2000"""
        if not sold_text:
            return None
        
        text = sold_text.strip().upper().replace(',', '')
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        
        for suffix, mult in multipliers.items():
            if suffix in text:
                try:
                    num = float(text.replace(suffix, ''))
                    return int(num * mult)
                except:
                    pass
        
        try:
            return int(float(text.replace('.', '')))
        except:
            return None
    
    def scrape_products_from_video(self, video_url: str, username: str) -> List[RawProduct]:
        """
        Extract products from video page JSON (like phase2_complete.py)
        Returns list of RawProduct with full details
        """
        video_id = parse_video_id(video_url)
        print(f"      🛒 Products from video: {video_id}")
        
        if not safe_get(self.driver, video_url, f"video {video_id}"):
            return []
        
        time.sleep(3)
        
        products = []
        
        try:
            # Extract JSON from page
            page_source = self.driver.page_source
            # TikTok 2024+ adds extra attributes, so use flexible pattern
            pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>'
            match = re.search(pattern, page_source, re.DOTALL)
            
            if not match:
                print(f"         ⚠️ No JSON data found")
                return []
            
            json_data = json.loads(match.group(1))
            
            # Navigate to video item data
            try:
                item_info = json_data["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]
            except KeyError:
                print(f"         ⚠️ Missing video data")
                return []
            
            # Extract video stats
            stats = item_info.get("stats", {})
            video_views = stats.get("playCount", 0)
            video_likes = stats.get("diggCount", 0)
            video_comments = stats.get("commentCount", 0)
            video_shares = stats.get("shareCount", 0)
            
            # Check for product anchors
            anchors = item_info.get("anchors", [])
            
            if not anchors:
                print(f"         ⏭️ No products in video")
                return []
            
            # Extract products from anchors
            for anchor in anchors:
                anchor_type = anchor.get("type")
                
                # Type 33 = Single product, Type 35 = Multiple products
                if anchor_type in [33, 35]:
                    try:
                        if anchor_type == 35 and "extra" in anchor:
                            # Multiple products
                            extra_data = json.loads(anchor["extra"])
                            for product_data in extra_data:
                                if "id" in product_data:
                                    product_detail = json.loads(product_data.get("extra", "{}"))
                                    
                                    product = RawProduct(
                                        username=username,
                                        video_id=video_id,
                                        video_url=video_url,
                                        video_views=video_views,
                                        video_likes=video_likes,
                                        video_comments=video_comments,
                                        video_shares=video_shares,
                                        has_shop=True,
                                        product_id=product_data["id"],
                                        product_title=product_detail.get("title", ""),
                                        seller_id=str(product_detail.get("seller_id", "")),
                                        price=product_detail.get("price", 0),
                                        currency=product_detail.get("currency", "VND"),
                                        product_url=product_detail.get("seo_url", ""),
                                        keyword=product_data.get("keyword", ""),
                                    )
                                    products.append(product)
                        
                        elif anchor_type == 33:
                            # Single product
                            extra_str = anchor.get("extra", "{}")
                            try:
                                extra_detail = json.loads(extra_str)
                            except:
                                extra_detail = {}
                            
                            product = RawProduct(
                                username=username,
                                video_id=video_id,
                                video_url=video_url,
                                video_views=video_views,
                                video_likes=video_likes,
                                video_comments=video_comments,
                                video_shares=video_shares,
                                has_shop=True,
                                product_id=anchor.get("id", ""),
                                product_title=extra_detail.get("title", anchor.get("keyword", "")),
                                seller_id=str(extra_detail.get("seller_id", "")),
                                price=extra_detail.get("price", 0),
                                currency=extra_detail.get("currency", "VND"),
                                product_url=extra_detail.get("seo_url", ""),
                                keyword=anchor.get("keyword", ""),
                            )
                            products.append(product)
                    
                    except Exception as e:
                        log_error(f"Product parse error: {e}", ERROR_LOG_PATH)
                        continue
            
            # Calculate features for each product
            for product in products:
                # Engagement metrics
                if product.video_views and product.video_views > 0:
                    product.engagement_total = (product.video_likes or 0) + (product.video_comments or 0) + (product.video_shares or 0)
                    product.engagement_rate = round(product.engagement_total / product.video_views, 4)
                    product.est_clicks = int(product.video_views * DEFAULT_CTR)
                    product.est_ctr = DEFAULT_CTR
                
                # Scrape sold_count from product page
                if product.product_url:
                    sold_count = self._scrape_product_sold_count(product.product_url)
                    if sold_count:
                        product.sold_count = sold_count
                        # Note: sold_delta would need historical data to calculate
                        # Will be computed in Spark/batch job by comparing with previous scrape
            
            print(f"         ✅ Found {len(products)} products")
        
        except Exception as e:
            log_error(f"Products extraction error: {e}", ERROR_LOG_PATH)
        
        return products
    
    def _scrape_product_sold_count(self, product_url: str) -> Optional[int]:
        """Scrape sold_count from product page"""
        if not product_url:
            return None
        
        try:
            self.driver.get(product_url)
            time.sleep(3)
            
            page_source = self.driver.page_source
            
            # Find sold count patterns
            sold_patterns = [
                r'([\d,.]+[KkMm]?)\s*(?:đã bán|sold)',  # "2.0K đã bán"
                r'"sold_count"[:\s]*["\s]*(\d+)',        # "sold_count": 93
            ]
            
            for pattern in sold_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    for m in matches:
                        result = self._parse_sold_count(m)
                        if result:
                            return result
        except:
            pass
        
        return None
    
    def scrape_products(self, username: str) -> List[RawProduct]:
        """Check if creator has TikTok Shop (legacy method - checks /shop page)"""
        url = f"https://www.tiktok.com/@{username}/shop"
        print(f"   🛒 Shop: @{username}")
        
        if not safe_get(self.driver, url, f"@{username}/shop"):
            return [RawProduct(username=username, has_shop=False)]
        
        time.sleep(2)
        current_url = self.driver.current_url
        
        if "/shop" not in current_url:
            print(f"      No shop found")
            return [RawProduct(username=username, has_shop=False)]
        
        print(f"      ✅ Has shop!")
        return [RawProduct(username=username, has_shop=True)]
    
    # ==================== KAFKA PUSH ====================
    
    def push_to_kafka(self, topic: str, key: str, data: dict):
        """Push data to Kafka"""
        success = self.kafka.send(KAFKA_TOPICS[topic], key, data)
        if success:
            self.stats[topic] = self.stats.get(topic, 0) + 1
        else:
            self.stats["errors"] += 1
    
    # ==================== FULL PIPELINE ====================
    
    def run_discovery(self, niches: List[str], mode: str = "hybrid"):
        """Run discovery mode"""
        self.round_number += 1
        print(f"\n{'─'*50}")
        print(f"📍 DISCOVERY ROUND {self.round_number}")
        print(f"{'─'*50}")
        
        # Build keywords từ các niches
        keywords = []
        for niche in niches:
            keywords.extend(NICHE_KEYWORDS.get(niche, []))
        
        if not keywords:
            keywords = ["review", "trending vietnam"]
        
        # Shuffle để không luôn lấy từ 1 niche
        random.shuffle(keywords)
        
        discoveries = []
        
        # Search
        if mode in ["search", "hybrid"]:
            for i in range(KEYWORDS_PER_ROUND):
                if is_interrupted():
                    break
                keyword = keywords[i % len(keywords)]
                discoveries.extend(self.discover_from_search(keyword))
                time.sleep(2)
        
        # FYP
        if mode in ["trending", "hybrid"] and not is_interrupted():
            discoveries.extend(self.discover_from_fyp())
        
        # Push to Kafka
        print(f"\n   📤 Pushing {len(discoveries)} discoveries...")
        for d in discoveries:
            self.push_to_kafka("discovery", d.username, asdict(d))
        
        self.kafka.flush()
        print(f"   ✅ Done!")
        
        return discoveries
    
    def run_full_scrape(self, username: str, scrape_videos: bool = True, 
                        scrape_comments: bool = False, scrape_products: bool = False,
                        max_videos: int = 20):
        """Scrape đầy đủ 1 creator"""
        print(f"\n{'─'*50}")
        print(f"📍 FULL SCRAPE: @{username}")
        print(f"{'─'*50}")
        
        # 1. Profile
        profile = self.scrape_profile(username)
        if profile:
            self.push_to_kafka("profiles", username, asdict(profile))
            print(f"   ✅ Profile scraped")
        
        # 2. Videos
        if scrape_videos and not is_interrupted():
            video_list = self.scrape_video_list(username, max_videos)
            
            for video_url, caption in video_list:
                if is_interrupted():
                    break
                
                video = self.scrape_video_stats(video_url, username, caption)
                if video:
                    self.push_to_kafka("videos", video.video_id, asdict(video))
                
                # Comments
                if scrape_comments:
                    comments = self.scrape_comments(video_url, username)
                    for c in comments:
                        self.push_to_kafka("comments", c.event_id, asdict(c))
                
                time.sleep(1)
            
            print(f"   ✅ Videos scraped: {len(video_list)}")
        
        # 3. Products - Extract from videos (not just check shop)
        if scrape_products and not is_interrupted():
            all_products = []
            
            # First check if user has shop
            shop_products = self.scrape_products(username)
            has_shop = shop_products[0].has_shop if shop_products else False
            
            # Then extract products from videos
            if scrape_videos and video_list:
                for video_url, _ in video_list[:5]:  # Check first 5 videos for products
                    if is_interrupted():
                        break
                    products = self.scrape_products_from_video(video_url, username)
                    all_products.extend(products)
            
            # Push to Kafka (exclude has_shop - only for internal logic)
            if all_products:
                for p in all_products:
                    key = f"{username}_{p.product_id or p.video_id or 'product'}"
                    product_data = {k: v for k, v in asdict(p).items() if k != 'has_shop'}
                    self.push_to_kafka("products", key, product_data)
                print(f"   ✅ Products scraped: {len(all_products)}")
            elif has_shop:
                # Just push shop info if no products found in videos
                shop_data = {k: v for k, v in asdict(shop_products[0]).items() if k != 'has_shop'}
                self.push_to_kafka("products", f"{username}_shop", shop_data)
                print(f"   ✅ Shop found (no products in videos)")
            else:
                print(f"   ⏭️ No shop/products found")
        
        self.kafka.flush()


# ===================== CLI =====================

def main():
    setup_signal_handler()
    
    parser = argparse.ArgumentParser(
        description="KOL Scraper - Unified TikTok Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Scraping mode")
    
    # Discovery command
    discovery_parser = subparsers.add_parser("discovery", help="Discover new KOLs")
    discovery_parser.add_argument("--mode", choices=["search", "trending", "hybrid"], default="hybrid")
    discovery_parser.add_argument("--niche", default="beauty,fashion,tech,food,lifestyle")
    discovery_parser.add_argument("--rounds", type=int, default=1)
    discovery_parser.add_argument("--kafka-broker", default=DEFAULT_KAFKA_BROKER)
    discovery_parser.add_argument("--dry-run", action="store_true")
    discovery_parser.add_argument("--headless", action="store_true")
    
    # Profile command
    profile_parser = subparsers.add_parser("profile", help="Scrape profiles")
    profile_parser.add_argument("--usernames", required=True, help="Comma-separated usernames")
    profile_parser.add_argument("--kafka-broker", default=DEFAULT_KAFKA_BROKER)
    profile_parser.add_argument("--dry-run", action="store_true")
    profile_parser.add_argument("--headless", action="store_true")
    
    # Videos command
    videos_parser = subparsers.add_parser("videos", help="Scrape videos")
    videos_parser.add_argument("--username", required=True)
    videos_parser.add_argument("--max-videos", type=int, default=50)
    videos_parser.add_argument("--with-comments", action="store_true")
    videos_parser.add_argument("--kafka-broker", default=DEFAULT_KAFKA_BROKER)
    videos_parser.add_argument("--dry-run", action="store_true")
    videos_parser.add_argument("--headless", action="store_true")
    
    # Full command
    full_parser = subparsers.add_parser("full", help="Full pipeline: discovery + scrape")
    full_parser.add_argument("--mode", choices=["search", "trending", "hybrid"], default="hybrid")
    full_parser.add_argument("--niche", default="beauty,fashion,tech,food,lifestyle")
    full_parser.add_argument("--max-kols", type=int, default=10)
    full_parser.add_argument("--max-videos", type=int, default=20)
    full_parser.add_argument("--with-comments", action="store_true")
    full_parser.add_argument("--with-products", action="store_true")
    full_parser.add_argument("--kafka-broker", default=DEFAULT_KAFKA_BROKER)
    full_parser.add_argument("--dry-run", action="store_true")
    full_parser.add_argument("--headless", action="store_true")
    
    # ============ DAEMON MODE - Real-time continuous scraping ============
    # NOTE: Daemon mode mặc định KHÔNG lấy comments/products nữa
    # Comments và Products sẽ được extract bởi consumers riêng (chạy song song)
    # Để chạy song song: .\scripts\start_parallel_scrapers.ps1
    daemon_parser = subparsers.add_parser("daemon", help="Run as daemon - continuous scraping")
    daemon_parser.add_argument("--mode", choices=["search", "trending", "hybrid"], default="hybrid")
    daemon_parser.add_argument("--niche", default="beauty,fashion,tech,food,lifestyle,gaming")
    daemon_parser.add_argument("--interval", type=int, default=300, help="Seconds between rounds (default: 300 = 5 min)")
    daemon_parser.add_argument("--max-kols-per-round", type=int, default=5, help="KOLs to scrape per round")
    daemon_parser.add_argument("--max-videos-per-kol", type=int, default=10)
    # Mặc định TẮT comments/products - để consumers làm song song
    daemon_parser.add_argument("--with-comments", action="store_true", default=False, help="Extract comments in main scraper (slower)")
    daemon_parser.add_argument("--with-products", action="store_true", default=False, help="Extract products in main scraper (slower)")
    daemon_parser.add_argument("--discovery-only", action="store_true", default=False, help="Only discovery, skip profile/videos (for parallel mode with consumers)")
    daemon_parser.add_argument("--kafka-broker", default=DEFAULT_KAFKA_BROKER)
    daemon_parser.add_argument("--dry-run", action="store_true")
    daemon_parser.add_argument("--headless", action="store_true", default=False)
    daemon_parser.add_argument("--use-profile", action="store_true", default=True, help="Use saved Chrome profile")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Create scraper - use profile for headless mode
    use_profile = getattr(args, 'use_profile', args.headless)  # Default: use profile when headless
    scraper = KOLScraper(
        kafka_broker=args.kafka_broker,
        dry_run=getattr(args, 'dry_run', False),
        headless=args.headless,
        use_profile=use_profile,
    )
    
    try:
        scraper.start()
        
        if args.command == "discovery":
            niches = [n.strip() for n in args.niche.split(",")]
            for _ in range(args.rounds):
                if is_interrupted():
                    break
                scraper.run_discovery(niches, args.mode)
        
        elif args.command == "profile":
            usernames = [u.strip() for u in args.usernames.split(",")]
            for username in usernames:
                if is_interrupted():
                    break
                profile = scraper.scrape_profile(username)
                if profile:
                    scraper.push_to_kafka("profiles", username, asdict(profile))
            scraper.kafka.flush()
        
        elif args.command == "videos":
            video_list = scraper.scrape_video_list(args.username, args.max_videos)
            for video_url, caption in video_list:
                if is_interrupted():
                    break
                video = scraper.scrape_video_stats(video_url, args.username, caption)
                if video:
                    scraper.push_to_kafka("videos", video.video_id, asdict(video))
                    
                    if args.with_comments:
                        comments = scraper.scrape_comments(video_url, args.username)
                        for c in comments:
                            scraper.push_to_kafka("comments", c.event_id, asdict(c))
            scraper.kafka.flush()
        
        elif args.command == "full":
            niches = [n.strip() for n in args.niche.split(",")]
            
            # Discovery
            discoveries = scraper.run_discovery(niches, args.mode)
            
            # Scrape top KOLs
            for i, d in enumerate(discoveries[:args.max_kols]):
                if is_interrupted():
                    break
                print(f"\n[{i+1}/{min(len(discoveries), args.max_kols)}]")
                scraper.run_full_scrape(
                    d.username,
                    scrape_videos=True,
                    scrape_comments=args.with_comments,
                    scrape_products=args.with_products,
                    max_videos=args.max_videos,
                )
        
        # ============ DAEMON MODE ============
        elif args.command == "daemon":
            niches = [n.strip() for n in args.niche.split(",")]
            round_num = 0
            
            discovery_only = getattr(args, 'discovery_only', False)
            
            print("\n" + "="*60)
            if discovery_only:
                print("🔄 DAEMON MODE - Discovery Only (Parallel Mode)")
            else:
                print("🔄 DAEMON MODE - Real-time Continuous Scraping")
            print("="*60)
            print(f"   Niches: {niches}")
            print(f"   Interval: {args.interval}s ({args.interval//60} min)")
            if discovery_only:
                print(f"   Mode: DISCOVERY ONLY → consumers sẽ xử lý song song")
                print(f"   Output: kol.discovery.raw (username only)")
            else:
                print(f"   KOLs/round: {args.max_kols_per_round}")
                print(f"   Videos/KOL: {args.max_videos_per_kol}")
                print(f"   Comments: {args.with_comments} {'(use --with-comments to enable)' if not args.with_comments else ''}")
                print(f"   Products: {args.with_products} {'(use --with-products to enable)' if not args.with_products else ''}")
            print("="*60)
            print("   Press Ctrl+C to stop")
            print("="*60 + "\n")
            
            while not is_interrupted():
                round_num += 1
                round_start = time.time()
                
                print(f"\n{'━'*60}")
                print(f"🔄 DAEMON ROUND {round_num} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'━'*60}")
                
                try:
                    # Discovery
                    discoveries = scraper.run_discovery(niches, args.mode)
                    
                    # Skip scraping if discovery-only mode (consumers will handle)
                    if not discovery_only:
                        # Scrape top KOLs from this round
                        for i, d in enumerate(discoveries[:args.max_kols_per_round]):
                            if is_interrupted():
                                break
                            print(f"\n[{i+1}/{min(len(discoveries), args.max_kols_per_round)}]")
                            scraper.run_full_scrape(
                                d.username,
                                scrape_videos=True,
                                scrape_comments=args.with_comments,
                                scrape_products=args.with_products,
                                max_videos=args.max_videos_per_kol,
                            )
                    
                    round_duration = time.time() - round_start
                    print(f"\n✅ Round {round_num} completed in {round_duration:.1f}s")
                    print(f"📊 Total stats: {scraper.stats}")
                    
                    # Wait for next round
                    if not is_interrupted():
                        wait_time = max(0, args.interval - round_duration)
                        if wait_time > 0:
                            print(f"\n⏳ Waiting {wait_time:.0f}s until next round...")
                            time.sleep(wait_time)
                
                except Exception as e:
                    print(f"\n❌ Round {round_num} error: {e}")
                    log_error(f"Daemon round {round_num} error: {e}", ERROR_LOG_PATH)
                    time.sleep(30)  # Wait before retry
            
            print(f"\n🛑 Daemon stopped after {round_num} rounds")
    
    finally:
        scraper.stop()


if __name__ == "__main__":
    main()

"""
SHARED SCRAPER UTILITIES

Module chung cho tất cả TikTok scrapers:
- WebDriver setup
- Common helpers (normalize_count, safe_get, etc.)
- Kafka producer wrapper

Được sử dụng bởi:
- discovery_kol_tiktok.py (Discovery)
- kol_enricher.py (Enricher)
- phase1_collect_basic_videos.py (Phase 1)
- phase1_5_collect_comments.py (Phase 1.5)
- phase2_complete.py (Phase 2)
"""

import json
import re
import signal
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

# ===================== CONFIG =====================

CHROME_DRIVER_PATH = r"C:\Program Files\chromedriver-win64\chromedriver.exe"

# Default Kafka broker (Redpanda on Docker)
DEFAULT_KAFKA_BROKER = "localhost:19092"

# Page timing
SCROLL_PAUSE = 1.0
PAGE_LOAD_WAIT = 3

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "scrape"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_PATH = OUTPUT_DIR / "errors.log"


# ===================== KAFKA IMPORT =====================

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("⚠️  kafka-python not installed. Run: pip install kafka-python")


# ===================== SIGNAL HANDLER =====================

INTERRUPTED = False

def setup_signal_handler():
    """Setup graceful shutdown handler"""
    global INTERRUPTED
    
    def handler(sig, frame):
        global INTERRUPTED
        print("\n\n⚠️  NHẬN TÍN HIỆU DỪNG (Ctrl+C) – đang dừng gracefully...")
        INTERRUPTED = True
    
    signal.signal(signal.SIGINT, handler)

def is_interrupted() -> bool:
    """Check if interrupted"""
    return INTERRUPTED


# ===================== HELPERS =====================

def log_error(msg: str, log_path: Path = ERROR_LOG_PATH):
    """Log error với timestamp"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def load_json(path: Path, default):
    """Load JSON file với fallback"""
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"Load JSON error ({path.name}): {e}")
        return default


def save_json(path: Path, data):
    """Save JSON file"""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_count(text: Optional[str]) -> Optional[int]:
    """
    Chuyển '1.2K', '3.4M', '1,234' -> int
    
    Examples:
        '1.2K' -> 1200
        '3.4M' -> 3400000
        '1,234' -> 1234
        '500' -> 500
    """
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
    except Exception:
        return None


def calculate_engagement_rate(likes: int, comments: int, shares: int, views: int) -> float:
    """
    Tính engagement rate = (likes + comments*2 + shares*3) / views * 100
    
    Weighted:
    - Comments count 2x (more effort)
    - Shares count 3x (most valuable action)
    """
    if not views or views == 0:
        return 0.0
    engagement = (likes or 0) + (comments or 0) * 2 + (shares or 0) * 3
    return round(engagement / views * 100, 4)


def calculate_discovery_score(
    followers: int,
    engagement_rate: float,
    video_views: int,
    is_verified: bool = False
) -> float:
    """
    Discovery Score = weighted combination of metrics (0-100)
    
    Ưu tiên:
    - Engagement rate cao (quan trọng nhất) - 50 points max
    - Followers vừa phải (10K-500K là sweet spot) - 30 points max
    - Video views cao (viral potential) - 15 points max
    - Verified badge (bonus nhỏ) - 5 points max
    """
    score = 0.0
    
    # Engagement rate (0-50 points)
    if engagement_rate >= 10:
        score += 50
    elif engagement_rate >= 5:
        score += 40
    elif engagement_rate >= 2:
        score += 30
    elif engagement_rate >= 1:
        score += 20
    else:
        score += 10
    
    # Followers sweet spot (0-30 points)
    if followers:
        if 50_000 <= followers <= 500_000:
            score += 30
        elif 500_000 < followers <= 1_000_000:
            score += 25
        elif 10_000 <= followers < 50_000:
            score += 20
        elif 1_000_000 < followers <= 5_000_000:
            score += 15
        else:
            score += 10
    
    # Video views (0-15 points)
    if video_views:
        if video_views >= 1_000_000:
            score += 15
        elif video_views >= 500_000:
            score += 12
        elif video_views >= 100_000:
            score += 10
        elif video_views >= 50_000:
            score += 7
        else:
            score += 5
    
    # Verified bonus (0-5 points)
    if is_verified:
        score += 5
    
    return round(score, 2)


# ===================== URL EXTRACTORS =====================

def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID từ TikTok URL"""
    match = re.search(r"/video/(\d+)", url)
    return match.group(1) if match else None


def extract_username_from_url(url: str) -> Optional[str]:
    """Extract username từ video URL"""
    match = re.search(r"/@([^/]+)/video/", url)
    return match.group(1) if match else None


def extract_username_from_profile_url(url: str) -> Optional[str]:
    """Extract username từ profile URL"""
    match = re.search(r"/@([^/?]+)", url)
    return match.group(1) if match else None


# ===================== WEBDRIVER =====================

import os
import random

# Random User-Agents để rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Chrome profile path for persistent sessions
CHROME_PROFILE_PATH = BASE_DIR / "data" / "chrome_profile"

def create_driver(headless: bool = False, chrome_driver_path: str = None, use_profile: bool = True, profile_dir: Optional[str] = None):
    """
    Create Chrome WebDriver với STEALTH anti-detection settings
    
    Args:
        headless: Run browser headless (note: TikTok may block headless)
        chrome_driver_path: Path to chromedriver. Auto-detect if None.
        use_profile: Use persistent Chrome profile (keeps cookies/session after verify)
    
    Returns:
        WebDriver instance
    
    Note:
        Set use_profile=True để giữ session sau khi verify TikTok.
        Lần đầu chạy với headless=False, verify captcha, sau đó có thể chạy headless.
    """
    # Auto-detect chromedriver path
    if chrome_driver_path is None:
        # Check environment variable first (Docker)
        if os.environ.get('CHROMEDRIVER_PATH'):
            chrome_driver_path = os.environ['CHROMEDRIVER_PATH']
        # Linux/Docker default
        elif os.path.exists('/usr/local/bin/chromedriver'):
            chrome_driver_path = '/usr/local/bin/chromedriver'
        # Windows default
        else:
            chrome_driver_path = CHROME_DRIVER_PATH
    
    options = Options()
    
    # ========== PERSISTENT PROFILE ==========
    # Use persistent profile to keep cookies/session after verification
    if use_profile:
        # Allow caller to override the default profile directory
        if profile_dir:
            profile_path = Path(profile_dir)
        else:
            profile_path = CHROME_PROFILE_PATH
        profile_path.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
    
    # In Docker with Xvfb, we don't need headless mode!
    # Xvfb provides virtual display, so Chrome thinks it has a real screen
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER')
    
    # TikTok DETECTS headless mode even with stealth!
    # So we DON'T use headless - instead run with real window but minimized
    if headless and not is_docker:
        # Don't use headless - TikTok blocks it
        # Use start-minimized instead so window doesn't disturb user
        options.add_argument("--start-minimized")
    
    # ========== STEALTH ANTI-DETECTION ==========
    # Core anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Fixed window size - NOT maximized to avoid video taking full screen
    # TikTok desktop layout needs at least 1280 width for comments sidebar
    options.add_argument("--window-size=1400,900")
    options.add_argument("--window-position=100,50")
    
    # Performance & stealth
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins-discovery")
    options.add_argument("--disable-default-apps")
    
    # Critical: Make Chrome look more real
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--disable-features=BlinkGenPropertyTrees")
    options.add_argument("--disable-ipc-flooding-protection")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-component-extensions-with-background-pages")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--no-first-run")
    options.add_argument("--safebrowsing-disable-auto-update")
    
    # WebGL and Canvas fingerprint randomization
    options.add_argument("--disable-webgl")
    options.add_argument("--disable-webgl2")
    
    # Language/locale spoofing
    options.add_argument("--lang=vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7")
    
    # Docker-specific settings
    if is_docker:
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--single-process")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--no-zygote")
        options.add_argument("--disable-software-rasterizer")
    
    # Exclude automation switches
    options.add_experimental_option("excludeSwitches", [
        "enable-automation", 
        "enable-logging",
        "enable-blink-features=AutomationControlled"
    ])
    options.add_experimental_option("useAutomationExtension", False)
    
    # Preferences to look more human
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.geolocation": 2,
        "webrtc.ip_handling_policy": "disable_non_proxied_udp",
        "webrtc.multiple_routes_enabled": False,
        "webrtc.nonproxied_udp_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)
    
    # Random User-Agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")

    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    
    # ========== INJECT STEALTH SCRIPTS ==========
    # Comprehensive stealth injection (like puppeteer-extra-plugin-stealth)
    stealth_js = """
        // Overwrite navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
        // Fake plugins array
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ]
        });
        
        // Fake languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['vi-VN', 'vi', 'en-US', 'en']
        });
        
        // Chrome runtime
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
        
        // Permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // WebGL Vendor & Renderer spoofing
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };
        
        // Hairline feature detection
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        // Remove Selenium/WebDriver traces
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """
    
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": stealth_js
    })
    
    # Don't override device metrics - let browser use natural window size
    # This prevents UI scaling issues on TikTok
    
    driver.set_page_load_timeout(60)
    return driver


def close_popup(driver):
    """Đóng popup login / cookie nếu có."""
    try:
        time.sleep(1)
        buttons = driver.find_elements(By.XPATH, "//button")
        for b in buttons:
            txt = (b.text or "").strip().lower()
            if any(k in txt for k in ["not now", "không phải bây giờ", "reject", "từ chối", "decline"]):
                try:
                    b.click()
                    time.sleep(0.5)
                except Exception:
                    continue
    except Exception:
        pass


def safe_get(driver, url: str, desc: str = "", max_retries: int = 3, wait_for_content: bool = True) -> bool:
    """
    Navigate với retry và wait for content
    
    Args:
        driver: WebDriver instance
        url: URL to navigate
        desc: Description for logging
        max_retries: Max retry attempts
        wait_for_content: Wait for TikTok content to load
    
    Returns:
        True if successful
    """
    for attempt in range(max_retries):
        if is_interrupted():
            return False
        try:
            driver.get(url)
            
            # Basic wait
            time.sleep(PAGE_LOAD_WAIT)
            close_popup(driver)
            
            # Wait for TikTok content to load (if requested)
            if wait_for_content:
                for _ in range(5):  # Wait up to 5 more seconds
                    time.sleep(1)
                    # Check if content loaded
                    try:
                        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/@"]')
                        if len(links) > 3:  # Found some user links
                            break
                    except:
                        pass
            
            return True
        except WebDriverException as e:
            print(f"   ⚠ Error loading {desc or url} (attempt {attempt+1}/{max_retries})")
            time.sleep(3 + attempt * 2)  # Increasing delay
    return False


def text_or_none(driver, xpath: str) -> Optional[str]:
    """Get text from element or None"""
    try:
        return driver.find_element(By.XPATH, xpath).text.strip()
    except Exception:
        return None


def safe_get_attribute(el, name: str) -> Optional[str]:
    """Get attribute from element safely"""
    try:
        return el.get_attribute(name)
    except Exception:
        return None


# ===================== PROFILE SCRAPER =====================

def collect_profile(driver, username: str, niche: str = "unknown") -> Optional[dict]:
    """
    Scrape full profile của creator
    
    Args:
        driver: WebDriver instance
        username: TikTok username
        niche: Predicted niche
    
    Returns:
        Profile dict or None
    """
    url = f"https://www.tiktok.com/@{username}"
    print(f"   👤 Lấy profile @{username}")

    if not safe_get(driver, url, desc=f"profile @{username}"):
        return None

    nickname = text_or_none(driver, "//h2[contains(@data-e2e,'user-subtitle')]")
    followers = text_or_none(driver, "//strong[contains(@data-e2e,'followers')]")
    following = text_or_none(driver, "//strong[contains(@data-e2e,'following')]")
    likes_total = text_or_none(driver, "//strong[contains(@data-e2e,'likes')]")
    bio = text_or_none(driver, "//h2[contains(@data-e2e,'user-bio')]")

    avatar_url = None
    try:
        avatar = driver.find_element(By.XPATH, "//img[contains(@data-e2e,'user-avatar')]")
        avatar_url = avatar.get_attribute("src")
    except Exception:
        pass

    verified = False
    try:
        driver.find_element(By.XPATH, "//span[contains(@data-e2e,'verified')]")
        verified = True
    except Exception:
        verified = False

    return {
        "username": username,
        "nickname": nickname,
        "followers": followers,
        "followers_count": normalize_count(followers),
        "following": following,
        "following_count": normalize_count(following),
        "likes_total": likes_total,
        "likes_count": normalize_count(likes_total),
        "bio": bio,
        "avatar_url": avatar_url,
        "verified": verified,
        "niche": niche,
    }


# ===================== VIDEO STATS SCRAPER =====================

def fetch_video_stats(driver, video_url: str) -> Optional[Dict]:
    """
    Mở trang video và lấy stats
    
    Args:
        driver: WebDriver instance
        video_url: TikTok video URL
    
    Returns:
        Dict with like_count, comment_count, share_count, view_count
    """
    if is_interrupted():
        return None

    print(f"      📺 Lấy stats video: {video_url}")
    
    try:
        driver.get(video_url)
        # Chờ tối đa 20s để page load
        wait = WebDriverWait(driver, 20)
        try:
            wait.until(EC.presence_of_all_elements_located((
                By.XPATH, 
                "//*[contains(@data-e2e,'like-count') or contains(@data-e2e,'comment-count') "
                "or contains(@data-e2e,'share-count') or contains(@data-e2e,'play-count')]"
            )))
        except TimeoutException:
            print(f"         ⚠ Timeout 20s chờ stats, bỏ qua video này.")
            return None
        
        time.sleep(2)
        close_popup(driver)
        
    except Exception as e:
        print(f"      ⚠ Lỗi mở video: {str(e)[:50]}")
        return None

    def count_by_xpath(xpath: str) -> Optional[int]:
        try:
            el = driver.find_element(By.XPATH, xpath)
            txt = el.text.strip()
            return normalize_count(txt)
        except Exception:
            return None

    stats = {
        "like_count": count_by_xpath("//*[contains(@data-e2e,'like-count')]"),
        "comment_count": count_by_xpath("//*[contains(@data-e2e,'comment-count')]"),
        "share_count": count_by_xpath("//*[contains(@data-e2e,'share-count')]"),
        "view_count": count_by_xpath("//*[contains(@data-e2e,'play-count')]"),
    }

    return stats


# ===================== KAFKA PRODUCER =====================

class KafkaStreamer:
    """Wrapper để push messages lên Kafka/Redpanda"""
    
    def __init__(self, broker: str = DEFAULT_KAFKA_BROKER, dry_run: bool = False):
        self.broker = broker
        self.dry_run = dry_run
        self.producer = None
        self.stats = {"sent": 0, "errors": 0}
        
        if not dry_run and KAFKA_AVAILABLE:
            self._connect()
    
    def _connect(self):
        """Connect to Kafka broker"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.broker,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3,
                retry_backoff_ms=500,
            )
            print(f"✅ Connected to Kafka: {self.broker}")
        except Exception as e:
            print(f"❌ Kafka connection failed: {e}")
            print("   Falling back to dry-run mode")
            self.dry_run = True
    
    def send(self, topic: str, key: str, value: dict) -> bool:
        """Send message to Kafka topic"""
        if self.dry_run:
            # Dry-run: chỉ print ra
            print(f"   📤 [DRY-RUN] {topic} | key={key}")
            self.stats["sent"] += 1
            return True
        
        if not self.producer:
            return False
        
        try:
            future = self.producer.send(topic, key=key, value=value)
            # Block for synchronous send
            future.get(timeout=10)
            self.stats["sent"] += 1
            return True
        except Exception as e:
            log_error(f"Kafka send error: {e}")
            self.stats["errors"] += 1
            return False
    
    def flush(self):
        """Flush pending messages"""
        if self.producer:
            self.producer.flush()
    
    def close(self):
        """Close producer"""
        if self.producer:
            self.producer.close()
            print(f"📊 Kafka stats: sent={self.stats['sent']}, errors={self.stats['errors']}")


# ===================== KAFKA CONSUMER =====================

def create_kafka_consumer(
    topics: List[str],
    group_id: str,
    broker: str = DEFAULT_KAFKA_BROKER,
    auto_offset_reset: str = 'earliest'
) -> Optional['KafkaConsumer']:
    """
    Create Kafka consumer
    
    Args:
        topics: List of topics to subscribe
        group_id: Consumer group ID
        broker: Kafka broker address
        auto_offset_reset: Where to start reading ('earliest' or 'latest')
    
    Returns:
        KafkaConsumer instance or None if not available
    """
    if not KAFKA_AVAILABLE:
        print("❌ Kafka not available")
        return None
    
    try:
        consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=broker,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            consumer_timeout_ms=5000,  # 5s timeout for poll
        )
        print(f"✅ Connected to Kafka consumer: {broker}")
        print(f"   Topics: {topics}")
        print(f"   Group: {group_id}")
        return consumer
    except Exception as e:
        print(f"❌ Kafka consumer connection failed: {e}")
        return None

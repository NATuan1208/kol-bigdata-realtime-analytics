"""
KOL Platform - Shared Configuration

Cấu hình chung cho tất cả scrapers và consumers.
Mỗi worker dùng Chrome profile riêng để chạy song song.
"""

import os
from pathlib import Path

# ===================== PATHS =====================

# Project root
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SCRAPE_DIR = DATA_DIR / "scrape"
SCRAPE_DIR.mkdir(parents=True, exist_ok=True)

# Logs
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ===================== CHROME PROFILES =====================
# Mỗi worker dùng profile riêng để chạy song song không conflict

CHROME_USER_DATA_DIR = Path(os.environ.get(
    "CHROME_USER_DATA_DIR",
    r"C:\Users\SelinaPhan\AppData\Local\Google\Chrome\User Data"
))

# 3 Chrome profiles cho 3 workers
CHROME_PROFILES = {
    # Scraper chính: discovery + profile + videos
    "scraper": {
        "user_data_dir": CHROME_USER_DATA_DIR,
        "profile_dir": "Default",
        "description": "Main scraper (discovery, profile, videos)",
    },
    # Comment extractor
    "comment": {
        "user_data_dir": CHROME_USER_DATA_DIR,
        "profile_dir": "Profile 1",
        "description": "Comment extractor consumer",
    },
    # Product extractor
    "product": {
        "user_data_dir": CHROME_USER_DATA_DIR,
        "profile_dir": "Profile 6",
        "description": "Product extractor consumer",
    },
}

# ChromeDriver path
CHROME_DRIVER_PATH = os.environ.get(
    "CHROME_DRIVER_PATH",
    r"C:\Program Files\chromedriver-win64\chromedriver.exe"
)


# ===================== KAFKA =====================

# Broker address (Redpanda)
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:19092")

# Topics - Raw data từ scraper
KAFKA_TOPICS = {
    "discovery": "kol.discovery.raw",
    "profiles": "kol.profiles.raw",
    "videos": "kol.videos.raw",
    "comments": "kol.comments.raw",
    "products": "kol.products.raw",
    "events": "kol.scraper.events",
}

# Consumer groups - mỗi consumer có group riêng
# LƯU Ý: Tất cả consumers lắng nghe discovery.raw cần GROUP ID KHÁC NHAU
# để mỗi consumer ĐỀU nhận được message (không phải load-balance)
# Thêm suffix -v3 để reset offset (đọc từ latest)
CONSUMER_GROUPS = {
    "video_stats_worker": "kol-video-stats-v3",
    "comment_extractor": "kol-comment-extractor-v3",
    "product_extractor": "kol-product-extractor-v3",
    "profile_enricher": "kol-profile-enricher-v3",
}


# ===================== SCRAPING SETTINGS =====================

# Timing
SCROLL_PAUSE = 1.0
PAGE_LOAD_WAIT = 3

# Limits - Optimized for trending calculation
# Giảm số video để refresh nhanh hơn (chỉ cần video gần đây)
MAX_VIDEOS_PER_KOL = 20          # 20 video gần nhất (đủ cho trending)
MAX_COMMENTS_PER_VIDEO = 50      # Top 50 comments cho sentiment
MAX_SEARCH_SCROLLS = 10          # ~20-30 KOL mới mỗi discovery
MAX_FYP_SCROLLS = 15             # FYP scrolls

# Trending config
MAX_TRACKED_KOLS = 150           # Giới hạn KOL được track (để refresh kịp)
REFRESH_INTERVAL_SECONDS = 300   # 5 phút refresh 1 lần (near real-time)

# Product metrics - Proxy CTR (TikTok không expose buy_count/click_count)
DEFAULT_CTR = 0.0387  # ~3.87% avg CTR for TikTok Shop


# ===================== NICHE KEYWORDS =====================

NICHE_KEYWORDS = {
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


# ===================== HELPER FUNCTIONS =====================

def get_chrome_profile(worker_name: str) -> dict:
    """
    Lấy config Chrome profile cho worker
    
    Args:
        worker_name: "scraper", "comment", hoặc "product"
    
    Returns:
        Dict với user_data_dir và profile_dir
    """
    if worker_name not in CHROME_PROFILES:
        raise ValueError(f"Unknown worker: {worker_name}. Use: {list(CHROME_PROFILES.keys())}")
    return CHROME_PROFILES[worker_name]


def get_profile_path(worker_name: str) -> Path:
    """
    Lấy đường dẫn đầy đủ tới Chrome profile
    
    Args:
        worker_name: "scraper", "comment", hoặc "product"
    
    Returns:
        Path object
    """
    profile = get_chrome_profile(worker_name)
    return profile["user_data_dir"] / profile["profile_dir"]

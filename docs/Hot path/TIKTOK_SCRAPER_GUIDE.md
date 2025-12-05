# 📱 Hướng Dẫn Thu Thập Dữ Liệu Social Media cho KOL Platform

> **Tác giả**: KOL Analytics Team  
> **Cập nhật**: Tháng 11/2025  
> **Phiên bản**: 2.0

---

## 📋 Mục Lục

1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Cài Đặt Môi Trường](#2-cài-đặt-môi-trường)
3. [Phase 1: Thu Thập Video & Profile](#3-phase-1-thu-thập-video--profile)
4. [Phase 1.5: Thu Thập Comments](#4-phase-15-thu-thập-comments)
5. [Phase 2: Thu Thập Sản Phẩm TikTok Shop](#5-phase-2-thu-thập-sản-phẩm-tiktok-shop)
6. [Dữ Liệu Đầu Ra](#6-dữ-liệu-đầu-ra)
7. [Hướng Phát Triển: YouTube & Twitter](#7-hướng-phát-triển-youtube--twitter)
8. [🔥 KOL Discovery: Tìm KOL Mới Đang Hot](#8--kol-discovery-tìm-kol-mới-đang-hot)

---

## 1. Tổng Quan Hệ Thống

### 1.1. Kiến Trúc Data Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                                  │
│                                                                          │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│   │   TikTok    │    │   YouTube   │    │   Twitter   │                 │
│   │  Scraper    │    │   (API v3)  │    │  (Nitter)   │                 │
│   │  Selenium   │    │   Official  │    │  Selenium   │                 │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│          │                  │                  │                         │
│          ▼                  ▼                  ▼                         │
│   ┌─────────────────────────────────────────────────────────┐           │
│   │                 KAFKA (Redpanda)                         │           │
│   │   Topics: events.social.raw, events.web.raw              │           │
│   └─────────────────────────────────────────────────────────┘            │
│                              │                                           │
│         ┌────────────────────┼────────────────────┐                     │
│         ▼                    ▼                    ▼                     │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐              │
│  │   SPARK     │      │   SPARK     │      │  CASSANDRA  │              │
│  │  STREAMING  │      │   BATCH     │      │  Real-time  │              │
│  │  (5 phút)   │      │   (Daily)   │      │   Metrics   │              │
│  └──────┬──────┘      └──────┬──────┘      └─────────────┘              │
│         │                    │                                          │
│         ▼                    ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │              DATA LAKEHOUSE (MinIO + Iceberg)            │           │
│  │                                                          │           │
│  │   kol-bronze/     kol-silver/      kol-gold/            │            │
│  │   (Raw JSON)      (Cleaned)        (Aggregated)          │           │
│  └─────────────────────────────────────────────────────────┘            │
│                              │                                          │
│                              ▼                                          │
│                     ┌─────────────┐                                     │
│                     │    TRINO    │ → BI Dashboard                      │
│                     │   (Query)   │                                     │
│                     └─────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2. Hai Luồng Thu Thập Dữ Liệu

Hệ thống có **2 luồng chính**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  📌 LUỒNG 1: THU THẬP TỪ KOL ĐÃ BIẾT (Phase 1, 1.5, 2)                │
│  ══════════════════════════════════════════════════════                │
│                                                                         │
│  Input: Danh sách KOLs có sẵn (seed list)                              │
│  → Scrape profiles, videos, comments, products                         │
│  → Dùng cho: Training models, Batch inference                          │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🔥 LUỒNG 2: TÌM KOL MỚI ĐANG HOT (Discovery)                          │
│  ═════════════════════════════════════════════                          │
│                                                                         │
│  Input: Keywords, Trending pages                                        │
│  → Discover KOLs mới từ search results, trending content               │
│  → Dùng cho: Real-time trending, KOL recommendations                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3. Mục Đích Thu Thập Dữ Liệu

| Phase | Dữ Liệu | Mục Đích | Mô Hình AI Sử Dụng |
|-------|---------|----------|-------------------|
| **Phase 1** | Video stats (views, likes, shares) | Trending Score, Success Score | LightGBM, Prophet |
| **Phase 1.5** | Comments (text) | Spam Detection | PhoBERT |
| **Phase 2** | Products (sold_count, price) | Success Score, Attribution | LightGBM, XGBoost |

### 1.3. Vì Sao Dùng Selenium Scraping?

TikTok **KHÔNG** cung cấp Public API. Các lựa chọn:

| Phương pháp | Khả dụng | Chi phí | Độ ổn định |
|-------------|----------|---------|------------|
| Official API | ❌ Cần Business Account | $$$$ | ⭐⭐⭐⭐⭐ |
| Unofficial API | ❌ Bị block liên tục | Free | ⭐ |
| **Selenium Scraping** | ✅ Hoạt động | Free | ⭐⭐⭐ |

**Giải pháp**: Dùng `undetected-chromedriver` để bypass bot detection của TikTok.

---

## 2. Cài Đặt Môi Trường

### 2.1. Yêu Cầu Hệ Thống

- **OS**: Windows 10/11
- **Python**: 3.11+
- **Chrome Browser**: Phiên bản mới nhất
- **RAM**: Tối thiểu 8GB

### 2.2. Cài Đặt Dependencies

```powershell
# Clone project (nếu chưa có)
cd E:\Project
git clone <repo_url> kol-platform
cd kol-platform

# Tạo virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Cài đặt packages
pip install selenium undetected-chromedriver
pip install confluent-kafka  # Cho Kafka integration
```

### 2.3. Cấu Trúc Thư Mục

```
kol-platform/
├── ingestion/
│   └── sources/
│       ├── phase1_collect_basic_videos.py   # Video & Profile scraper
│       ├── phase1_5_collect_comments.py     # Comment scraper
│       └── phase2_complete.py               # Product scraper
├── data/
│   └── scrape/
│       ├── phase1_videos_basic.json         # Output Phase 1
│       ├── phase1_profiles.json             # KOL profiles
│       ├── phase1_5_comments.json           # Output Phase 1.5
│       ├── phase2_products_complete.json    # Output Phase 2
│       └── checkpoint_state.json            # Resume state
```

---

## 3. Phase 1: Thu Thập Video & Profile

### 3.1. Mô Tả

Thu thập thông tin cơ bản của video và profile KOL từ TikTok.

**File**: `ingestion/sources/phase1_collect_basic_videos.py`

### 3.2. Dữ Liệu Thu Thập

#### Profile KOL:
```json
{
  "username": "minhthu.chloe",
  "nickname": "Minh Thư Chloe",
  "followers": 1200000,
  "following": 150,
  "likes_total": 25000000,
  "bio": "Beauty blogger | Paris",
  "verified": true,
  "niche": "beauty"
}
```

#### Video:
```json
{
  "video_id": "7554728709660364052",
  "video_url": "https://www.tiktok.com/@minhthu.chloe/video/7554728709660364052",
  "username": "minhthu.chloe",
  "niche": "beauty",
  "caption": "Tủ đồ áo len sắm trước khi qua Paris 🦊...",
  "like_count": 2112,
  "comment_count": 10,
  "share_count": 64,
  "view_count": null
}
```

### 3.3. Cách Chạy

```powershell
cd E:\Project\kol-platform

# Chạy thu thập (mặc định 100 video/KOL)
py ingestion/sources/phase1_collect_basic_videos.py

# Chạy với giới hạn video
py ingestion/sources/phase1_collect_basic_videos.py --max-videos 50
```

### 3.4. Cơ Chế Hoạt Động

1. **Seed KOLs**: Danh sách KOLs được chia theo niche (beauty, fashion, tech, food...)
2. **Scrape Profile**: Mở trang profile → Parse JSON từ `__UNIVERSAL_DATA_FOR_REHYDRATION__`
3. **Scrape Videos**: Scroll xuống → Lấy danh sách video → Parse stats
4. **Checkpoint**: Lưu tiến trình sau mỗi KOL (resume nếu bị gián đoạn)

### 3.5. Kết Quả Hiện Tại

```
📊 Phase 1 Statistics:
├── Total Videos: 790
├── Total KOLs: ~50
├── Niches: beauty, fashion, lifestyle, tech, food_review, gaming, travel, pet
└── Output: data/scrape/phase1_videos_basic.json (8,692 lines)
```

---

## 4. Phase 1.5: Thu Thập Comments

### 4.1. Mô Tả

Thu thập text comment từ video để train **PhoBERT Spam Classifier**.

**File**: `ingestion/sources/phase1_5_collect_comments.py`

### 4.2. Dữ Liệu Thu Thập

```json
{
  "scraped_at": "2025-11-27T08:07:49Z",
  "total_videos": 3,
  "total_comments": 32,
  "data": [
    {
      "video_id": "7554728709660364052",
      "comments": [
        "c có chứng chỉ tiếng pháp k🥲",
        "đầu c ơi",
        "In4 áo khoác da đầu video, mn copy mã này lên sôpy có nhé: BKY-RNT-MSS",
        "mới qua đó chắc còn rảnh nên cổ vid đều quá 😍"
      ]
    }
  ]
}
```

### 4.3. Cách Chạy

```powershell
# Thu thập 10 video đầu tiên
py ingestion/sources/phase1_5_collect_comments.py --max 10 --start 0

# Thu thập 50 video, bắt đầu từ video thứ 100
py ingestion/sources/phase1_5_collect_comments.py --max 50 --start 100

# Chạy headless (không hiện browser)
py ingestion/sources/phase1_5_collect_comments.py --max 20 --headless
```

### 4.4. Cơ Chế Hoạt Động

1. **Load Phase 1 data**: Đọc danh sách video URLs
2. **Mở video page**: Navigate đến từng video
3. **Extract comments**: 
   - **Method 1**: Parse từ JSON `__UNIVERSAL_DATA_FOR_REHYDRATION__` (nhanh nhất)
   - **Method 2**: DOM scraping với selector `span[data-e2e="comment-level-1"]` (fallback)
4. **Lưu kết quả**: Chỉ lưu text comment (không metadata)

### 4.5. Tại Sao Chỉ Lấy Text?

- **Mục đích**: Train PhoBERT spam classifier
- **Không cần**: author, likes, timestamp
- **Lợi ích**: File nhỏ hơn, scrape nhanh hơn

---

## 5. Phase 2: Thu Thập Sản Phẩm TikTok Shop

### 5.1. Mô Tả

Thu thập thông tin sản phẩm từ video có gắn TikTok Shop để tính **Success Score**.

**File**: `ingestion/sources/phase2_complete.py`

### 5.2. Vấn Đề Gặp Phải

> ⚠️ **QUAN TRỌNG**: TikTok **KHÔNG** public các metrics quan trọng:
> - `click_count` (số click vào sản phẩm)
> - `buy_count` (số lượt mua)
> - `uv` (unique visitors)
> - `pv` (page views)
>
> Các metrics này chỉ có trong **Seller Dashboard** (cần quyền seller).

### 5.3. Giải Pháp: Proxy Metrics

Thay vì dữ liệu thật, dùng **proxy metrics**:

| Metric Thật | Proxy Metric | Công Thức |
|-------------|--------------|-----------|
| `click_count` | `est_clicks` | `views × CTR (3%)` |
| `buy_count` | `sold_delta` | `sold_count_today - sold_count_yesterday` |
| Conversion Rate | `est_ctr` | `(likes + comments + shares) / views` |

### 5.4. Dữ Liệu Thu Thập

```json
{
  "video_url": "https://www.tiktok.com/@chouchinchan/video/7570670053759143175",
  "video_id": "7570670053759143175",
  "author": "chouchinchan",
  "video_stats": {
    "views": 28200,
    "likes": 766,
    "comments": 22,
    "shares": 10
  },
  "has_products": true,
  "products": [
    {
      "product_id": "1732961085040526393",
      "product_title": "[LG Makeup VN] Nhũ bắt sáng highlight Glint...",
      "seller_id": 7495469153399048249,
      "price": 490000,
      "currency": "VND",
      "sold_count": 93
    }
  ],
  "features": {
    "engagement_rate": 0.0283,
    "est_clicks": 1085,
    "est_ctr": 0.0385,
    "sold_count": 93
  }
}
```

### 5.5. Cách Chạy

```powershell
# Thu thập 10 video có sản phẩm
py ingestion/sources/phase2_complete.py --max 10

# Bỏ qua scrape sold_count (nhanh hơn)
py ingestion/sources/phase2_complete.py --max 50 --no-sold

# Chạy headless
py ingestion/sources/phase2_complete.py --max 20 --headless
```

### 5.6. Cơ Chế Hoạt Động

1. **Load Phase 1 videos**: Lọc video có khả năng có sản phẩm
2. **Extract products từ video page**: Parse JSON tìm `promotionInfo`
3. **Scrape product page**: Lấy `sold_count`, `price` từ trang sản phẩm
4. **Tính features**: `engagement_rate`, `est_clicks`, `est_ctr`
5. **Track timeseries**: Lưu `sold_count` theo ngày để tính `sold_delta`

---

## 6. Dữ Liệu Đầu Ra

### 6.1. Tổng Hợp Output Files

| File | Kích thước | Mô tả |
|------|------------|-------|
| `phase1_videos_basic.json` | ~8,700 lines | 790 videos với stats |
| `phase1_profiles.json` | ~2,000 lines | ~50 KOL profiles |
| `phase1_5_comments.json` | ~54 lines | 32 comments (test) |
| `phase2_products_complete.json` | ~85 lines | 2 products (test) |

### 6.2. Schema Summary

```
📦 phase1_videos_basic.json
├── video_id: string
├── video_url: string
├── username: string
├── niche: string (beauty|fashion|tech|food|...)
├── caption: string
├── like_count: number
├── comment_count: number
├── share_count: number
└── view_count: number | null

📦 phase1_5_comments.json
├── scraped_at: datetime
├── total_videos: number
├── total_comments: number
└── data: [
      └── video_id: string
      └── comments: string[]
    ]

📦 phase2_products_complete.json
├── scraped_at: datetime
├── total_videos_processed: number
├── total_products_found: number
└── videos: [
      ├── video_url: string
      ├── video_stats: {views, likes, comments, shares}
      ├── products: [
      │     ├── product_id: string
      │     ├── product_title: string
      │     ├── seller_id: number
      │     ├── price: number
      │     └── sold_count: number
      │   ]
      └── features: {engagement_rate, est_clicks, est_ctr}
    ]
```

---

## 7. Hướng Phát Triển: YouTube & Twitter

### 7.1. Tổng Quan Multimedia

Để xây dựng **KOL Analytics đa nền tảng**, cần mở rộng thu thập từ:

| Platform | API | Chi phí | Độ khó |
|----------|-----|---------|--------|
| TikTok | ❌ Scraping | Free | 🟡 Medium |
| **YouTube** | ✅ Official API v3 | Free (quota) | 🟢 Easy |
| **Twitter/X** | ⚠️ Nitter (mirror) | Free | 🔴 Hard |

### 7.2. YouTube - Dữ Liệu Cần Thu Thập

**Công cụ**: YouTube Data API v3 (Official)

**Setup**:
1. Vào https://console.cloud.google.com/
2. Tạo project → Enable "YouTube Data API v3"
3. Tạo API Key → Set vào environment variable

**Dữ liệu Streaming** (real-time trending):
```python
{
  "video_id": "dQw4w9WgXcQ",
  "view_count": 1500000,      # Realtime views
  "like_count": 50000,
  "comment_count": 2000,
  "published_at": "2025-01-15T10:00:00Z",
  "duration": "PT3M45S"       # ISO 8601
}
```

**Dữ liệu Batch** (TrustScore, SuccessScore):
```python
# Video-level
{
  "title": "Review Son Mới",
  "description": "...",
  "tags": ["beauty", "review", "lipstick"],
  "category": "Howto & Style",
  "view_count": 100000,
  "like_count": 5000,
  "comment_count": 500
}

# Channel-level
{
  "channel_id": "UC...",
  "subscriber_count": 500000,
  "video_count": 200,
  "total_views": 50000000,
  "country": "VN"
}

# Comments (cho PhoBERT)
{
  "video_id": "...",
  "comments": ["Hay quá!", "Mua ở đâu vậy?", ...]
}
```

**CLI dự kiến**:
```powershell
# Set API key
$env:YOUTUBE_API_KEY = "AIza..."

# Chạy scraper
py ingestion/sources/youtube_scraper.py --max 100 --kafka
```

### 7.3. Twitter - Dữ Liệu Cần Thu Thập

**Công cụ**: Nitter (free Twitter frontend) + Selenium

> ⚠️ Twitter API v2 tính phí **$100/tháng** minimum, nên dùng Nitter để scrape miễn phí.

**Dữ liệu Streaming** (real-time trending):
```python
{
  "tweet_id": "1234567890",
  "text": "Review sản phẩm mới...",
  "like_count": 500,
  "retweet_count": 100,
  "reply_count": 50,
  "quote_count": 20,
  "created_at": "2025-01-15T10:00:00Z"
}
```

**Dữ liệu Batch** (TrustScore):
```python
# User profile
{
  "username": "beauty_blogger_vn",
  "followers_count": 50000,
  "following_count": 500,
  "tweet_count": 2000,
  "verified": false
}

# Tweet history (cho anomaly detection)
{
  "tweets": [
    {"like_count": 100, "retweet_count": 20, "date": "2025-01-15"},
    {"like_count": 150, "retweet_count": 30, "date": "2025-01-14"},
    ...
  ]
}

# Replies (cho PhoBERT spam detection)
{
  "tweet_id": "...",
  "replies": ["Mua ở đâu?", "Spam link...", ...]
}
```

**CLI dự kiến**:
```powershell
# Chạy scraper (sẽ tự tìm Nitter instance hoạt động)
py ingestion/sources/twitter_scraper.py --max 50 --headless --kafka
```

### 7.4. Feature Mapping cho AI Models

| Feature | TikTok | YouTube | Twitter | Model |
|---------|--------|---------|---------|-------|
| `view_velocity` | ✅ views | ✅ viewCount | ❌ | **TrendingScore** |
| `like_velocity` | ✅ likes | ✅ likeCount | ✅ like_count | **TrendingScore** |
| `retweet_velocity` | ❌ | ❌ | ✅ retweet_count | **TrendingScore** |
| `spam_ratio` | ✅ comments | ✅ comments | ✅ replies | **TrustScore** (PhoBERT) |
| `engagement_rate` | ✅ | ✅ | ✅ | **TrustScore** (XGBoost) |
| `follower_count` | ✅ | ✅ subscriber | ✅ followers | **TrustScore** |
| `sold_count` | ✅ TikTok Shop | ❌ proxy | ❌ proxy | **SuccessScore** (LightGBM) |
| `est_clicks` | ✅ | ✅ CTR | ✅ link clicks | **SuccessScore** |

### 7.5. Kafka Topics (Multimedia)

```
# Streaming Topics (5 phút refresh)
events.social.tiktok      # TikTok video stats
events.social.youtube     # YouTube video stats
events.social.twitter     # Twitter tweet stats

# Batch Topics (daily)
batch.comments.all        # Comments từ tất cả platforms
batch.products.tiktok     # TikTok Shop products
batch.profiles.all        # KOL profiles từ tất cả platforms
```

---

## 📎 Tài Liệu Tham Khảo

- [TikTok Scraping với Selenium](https://github.com/davidteather/TikTok-Api)
- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [Nitter Instances](https://github.com/zedeus/nitter/wiki/Instances)
- [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver)

---

## 🚀 Quick Start Commands

```powershell
# Activate environment
cd E:\Project\kol-platform
.\.venv\Scripts\Activate.ps1

# Phase 1: Thu thập videos
py ingestion/sources/phase1_collect_basic_videos.py

# Phase 1.5: Thu thập comments
py ingestion/sources/phase1_5_collect_comments.py --max 50

# Phase 2: Thu thập products
py ingestion/sources/phase2_complete.py --max 20

# Kiểm tra output
Get-Content data/scrape/phase1_videos_basic.json | Select -First 50
Get-Content data/scrape/phase1_5_comments.json
Get-Content data/scrape/phase2_products_complete.json
```

---

**✅ Tài liệu này mô tả toàn bộ quy trình thu thập dữ liệu TikTok cho KOL Platform, từ setup môi trường đến output cuối cùng, và hướng phát triển mở rộng sang YouTube & Twitter.**

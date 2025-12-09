# YouTube Integration - Hướng dẫn đầy đủ

## 📋 Tổng quan

Tài liệu này mô tả chi tiết việc tích hợp YouTube vào hệ thống KOL Analytics Platform, bao gồm:
- Kiến trúc hệ thống
- Các components và luồng dữ liệu
- Hướng dẫn cài đặt và chạy
- Troubleshooting

---

## 🏗️ Kiến trúc hệ thống

### Tổng quan luồng dữ liệu

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KOL ANALYTICS PLATFORM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────┐ │
│  │   TikTok    │     │   YouTube   │     │   Kafka     │     │   Spark   │ │
│  │  Discovery  │     │  Discovery  │     │  (Redpanda) │     │ Streaming │ │
│  │  (Selenium) │     │    (API)    │     │             │     │           │ │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └─────┬─────┘ │
│         │                   │                   │                   │       │
│         └───────────────────┴───────────────────┘                   │       │
│                             │                                       │       │
│                             ▼                                       │       │
│                    kol.discovery.raw                                │       │
│                             │                                       │       │
│         ┌───────────────────┴───────────────────┐                   │       │
│         ▼                                       ▼                   │       │
│  ┌─────────────┐                         ┌─────────────┐            │       │
│  │   TikTok    │                         │   YouTube   │            │       │
│  │Stats Worker │                         │Stats Worker │            │       │
│  │ (Selenium)  │                         │   (API)     │            │       │
│  └──────┬──────┘                         └──────┬──────┘            │       │
│         │                                       │                   │       │
│         └───────────────────┬───────────────────┘                   │       │
│                             │                                       │       │
│                             ▼                                       │       │
│              ┌──────────────────────────┐                           │       │
│              │     Kafka Topics         │                           │       │
│              │  - kol.profiles.raw      │◄──────────────────────────┘       │
│              │  - kol.videos.raw        │                                   │
│              │  - kol.comments.raw      │                                   │
│              └──────────────┬───────────┘                                   │
│                             │                                               │
│                             ▼                                               │
│              ┌──────────────────────────┐                                   │
│              │     Spark Streaming      │                                   │
│              │  - Bronze Layer (raw)    │                                   │
│              │  - Compute Scores        │                                   │
│              │  - Write to Redis        │                                   │
│              └──────────────┬───────────┘                                   │
│                             │                                               │
│                             ▼                                               │
│              ┌──────────────────────────┐     ┌─────────────┐               │
│              │         Redis            │────▶│  Dashboard  │               │
│              │   (Real-time scores)     │     │  (Streamlit)│               │
│              └──────────────────────────┘     └─────────────┘               │
│                                                                             │
│              ┌──────────────────────────┐                                   │
│              │    Metrics Refresh       │                                   │
│              │  (Trigger re-scrape)     │───────────────────────────────────┤
│              └──────────────────────────┘                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### So sánh TikTok vs YouTube

| Component | TikTok | YouTube |
|-----------|--------|---------|
| **Discovery** | Selenium scraping | YouTube Data API v3 |
| **Stats Worker** | Selenium scraping | YouTube Data API v3 |
| **Comments Worker** | Selenium scraping | YouTube Data API v3 |
| **Rate Limiting** | Slow (browser-based) | Fast (API-based) |
| **Channel ID** | Không cần | Tự resolve từ @handle |

---

## 📁 Cấu trúc Files

```
kol-platform/
├── ingestion/
│   ├── sources/
│   │   ├── youtube_api.py              # YouTube API Client wrapper
│   │   ├── youtube_discovery_api.py    # Discover trending YouTube channels
│   │   └── metrics_refresh.py          # Trigger re-scrape cho cả TikTok & YouTube
│   │
│   └── consumers/
│       ├── youtube_stats_worker.py     # Scrape channel info & videos
│       └── youtube_comments_worker.py  # Scrape video comments
│
├── streaming/
│   └── spark_jobs/
│       └── kol_streaming.py            # Spark job xử lý cả TikTok & YouTube
│
├── infra/
│   ├── docker-compose.kol.yml          # Docker compose với youtube-scraper service
│   ├── dockerfiles/
│   │   └── Dockerfile.scraper          # Dockerfile cho scraper containers
│   └── scripts/
│       └── youtube_entrypoint.sh       # Entrypoint script cho YouTube container
│
└── requirements/
    └── youtube.txt                     # Python dependencies cho YouTube
```

---

## 🔧 Các Components chi tiết

### 1. YouTube API Client (`youtube_api.py`)

Wrapper cho YouTube Data API v3:

```python
from ingestion.sources.youtube_api import YouTubeAPI

api = YouTubeAPI()  # Tự động đọc YOUTUBE_API_KEY từ env

# Lấy channel info bằng channel_id
channel = api.get_channel_info("UCX6OQ3DkcsbYNE6H8uQQuVA")

# Lấy channel info bằng @handle (username)
channel = api.get_channel_by_handle("mrbeast")

# Lấy videos của channel
video_ids = api.get_channel_videos(channel_id, max_results=50)

# Lấy stats của videos
videos = api.get_video_stats(video_ids)

# Lấy comments của video
comments = api.get_comments(video_id, max_results=100)
```

**API Quota Cost:**
- `channels.list`: 1 unit
- `videos.list`: 1 unit  
- `search.list`: 100 units
- `commentThreads.list`: 1 unit
- Daily quota: 10,000 units (có thể request tăng)

### 2. YouTube Discovery (`youtube_discovery_api.py`)

Tìm trending channels từ YouTube:

```bash
# Dry run (test)
python -m ingestion.sources.youtube_discovery_api --dry-run

# One-time discovery
python -m ingestion.sources.youtube_discovery_api --max-channels 20

# Daemon mode (continuous)
python -m ingestion.sources.youtube_discovery_api daemon --interval 21600
```

**Luồng hoạt động:**
1. Gọi `videos.list` với `chart=mostPopular` để lấy trending videos
2. Extract unique channels từ videos
3. Gọi `channels.list` để lấy channel details (@handle)
4. Push lên Kafka topic `kol.discovery.raw`

### 3. YouTube Stats Worker (`youtube_stats_worker.py`)

Consumer xử lý YouTube KOLs từ `kol.discovery.raw`:

```bash
python -m ingestion.consumers.youtube_stats_worker --max-videos 50
```

**Luồng hoạt động:**
1. Consume message từ `kol.discovery.raw` (filter `platform="youtube"`)
2. Nếu có `channel_id` → dùng luôn
3. Nếu không có → **tự resolve bằng `get_channel_by_handle(username)`**
4. Gọi API lấy channel info, videos
5. Push lên `kol.profiles.raw` và `kol.videos.raw`

### 4. YouTube Comments Worker (`youtube_comments_worker.py`)

Consumer xử lý comments từ `kol.videos.raw`:

```bash
python -m ingestion.consumers.youtube_comments_worker --max-comments 100
```

**Luồng hoạt động:**
1. Consume message từ `kol.videos.raw` (filter `platform="youtube"`)
2. Gọi API lấy top comments của video
3. Push lên `kol.comments.raw`

### 5. Metrics Refresh (`metrics_refresh.py`)

Trigger re-scrape cho KOLs đang được track:

```bash
# One-time
python -m ingestion.sources.metrics_refresh

# Loop mỗi 5 phút
python -m ingestion.sources.metrics_refresh --interval 300
```

**Luồng hoạt động:**
1. Đọc danh sách KOLs từ Redis (`streaming_scores:*`)
2. Push username + platform lên `kol.discovery.raw`
3. Stats Worker sẽ tự động scrape lại
4. Spark tính velocity từ data mới

---

## 🐳 Docker Setup

### 1. Environment Variables

Tạo file `.env` hoặc set trong docker-compose:

```env
# YouTube API
YOUTUBE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXX

# Kafka
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092

# Redis
REDIS_HOST=kol-redis
REDIS_PORT=6379
```

### 2. Docker Compose Service

Service `youtube-scraper` trong `docker-compose.kol.yml`:

```yaml
youtube-scraper:
  build:
    context: ..
    dockerfile: infra/dockerfiles/Dockerfile.scraper
  container_name: youtube-scraper
  hostname: youtube-scraper
  environment:
    - YOUTUBE_API_KEY=${YOUTUBE_API_KEY}
    - KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
    - REDIS_HOST=kol-redis
    - REDIS_PORT=6379
    - YOUTUBE_REGION=VN
  depends_on:
    redpanda:
      condition: service_healthy
  networks:
    - kol-network
  command: ["/app/infra/scripts/youtube_entrypoint.sh"]
  restart: unless-stopped
```

### 3. Entrypoint Script

`youtube_entrypoint.sh` chạy 4 workers với supervisord:

```bash
#!/bin/bash
# Workers:
# 1. YouTube Discovery (mỗi 6h)
# 2. YouTube Stats Worker
# 3. YouTube Comments Worker  
# 4. Metrics Refresh (mỗi 5 phút)

exec supervisord -c /etc/supervisor/conf.d/youtube.conf
```

### 4. Build và Run

```bash
# Build image
docker-compose -f infra/docker-compose.kol.yml build youtube-scraper

# Start container
docker-compose -f infra/docker-compose.kol.yml up -d youtube-scraper

# Xem logs
docker logs youtube-scraper -f

# Restart sau khi sửa code
docker-compose -f infra/docker-compose.kol.yml up -d --force-recreate youtube-scraper
```

---

## 🚀 Hướng dẫn chạy từ đầu

### Bước 1: Chuẩn bị YouTube API Key

1. Vào [Google Cloud Console](https://console.cloud.google.com)
2. Tạo project mới hoặc chọn project có sẵn
3. Enable **YouTube Data API v3**
4. Tạo API Key (Credentials → Create Credentials → API Key)
5. Copy API Key

### Bước 2: Cấu hình Environment

```bash
# Set environment variable
export YOUTUBE_API_KEY="AIzaSyXXXXXXXXXXXXXXXXXXX"

# Hoặc tạo file .env
echo "YOUTUBE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXX" >> .env
```

### Bước 3: Start Infrastructure

```bash
cd kol-platform

# Start base services (Redis, Kafka/Redpanda, Spark)
docker-compose -f infra/docker-compose.kol.yml up -d redis redpanda spark-master

# Đợi services healthy
docker-compose -f infra/docker-compose.kol.yml ps
```

### Bước 4: Start YouTube Scraper

```bash
# Build và start
docker-compose -f infra/docker-compose.kol.yml up -d --build youtube-scraper

# Verify
docker logs youtube-scraper -f
```

### Bước 5: Start Spark Streaming

```bash
# Start Spark streaming job
docker-compose -f infra/docker-compose.kol.yml up -d kol-spark-streaming

# Xem logs
docker logs kol-spark-streaming -f
```

### Bước 6: Start Dashboard

```bash
# Start dashboard
docker-compose -f infra/docker-compose.kol.yml up -d kol-dashboard

# Truy cập: http://localhost:8501
```

---

## 📊 Kafka Topics & Message Format

### Topic: `kol.discovery.raw`

```json
{
  "event_id": "uuid",
  "event_time": "2024-01-01T00:00:00Z",
  "event_type": "discovery|refresh",
  "platform": "youtube|tiktok",
  "username": "mrbeast",
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",  // Optional cho refresh
  "url": "https://www.youtube.com/@mrbeast"
}
```

### Topic: `kol.profiles.raw`

```json
{
  "event_id": "uuid",
  "event_time": "2024-01-01T00:00:00Z",
  "event_type": "profile",
  "platform": "youtube",
  "username": "mrbeast",
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "followers_raw": "100000000",
  "following_raw": "0",
  "likes_raw": "50000000000",
  "bio": "Channel description...",
  "avatar_url": "https://...",
  "profile_url": "https://youtube.com/@mrbeast"
}
```

### Topic: `kol.videos.raw`

```json
{
  "event_id": "uuid",
  "event_time": "2024-01-01T00:00:00Z",
  "event_type": "video",
  "platform": "youtube",
  "username": "mrbeast",
  "video_id": "dQw4w9WgXcQ",
  "video_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
  "title": "Video title",
  "view_count": 1000000,
  "like_count": 50000,
  "comment_count": 5000,
  "duration": 300,
  "published_at": "2024-01-01T00:00:00Z"
}
```

### Topic: `kol.comments.raw`

```json
{
  "event_id": "uuid",
  "event_time": "2024-01-01T00:00:00Z",
  "event_type": "comment",
  "platform": "youtube",
  "video_id": "dQw4w9WgXcQ",
  "username": "mrbeast",
  "comment_id": "UgzXXX",
  "author": "John Doe",
  "text": "Great video!",
  "like_count": 100,
  "published_at": "2024-01-01T00:00:00Z"
}
```

---

## 🔍 Troubleshooting

### Lỗi: "YOUTUBE_API_KEY not found"

```bash
# Kiểm tra env
docker exec youtube-scraper env | grep YOUTUBE

# Fix: Set trong docker-compose.kol.yml
environment:
  - YOUTUBE_API_KEY=${YOUTUBE_API_KEY}
```

### Lỗi: "quotaExceeded"

YouTube API có giới hạn 10,000 quota/ngày. Solutions:
1. Giảm `max_channels`, `max_videos`, `max_comments`
2. Tăng interval giữa các rounds
3. Request quota increase từ Google

### Lỗi: "Channel not found for @username"

Có thể do:
1. Username sai hoặc channel đã bị xóa
2. Channel chưa có custom URL (@handle)
3. API error tạm thời

### Lỗi: Redis connection refused

```bash
# Kiểm tra Redis
docker exec kol-redis redis-cli ping

# Kiểm tra network
docker network inspect kol-network
```

### Xem logs chi tiết

```bash
# All logs
docker logs youtube-scraper -f

# Filter by worker
docker logs youtube-scraper 2>&1 | grep "Stats Worker"
docker logs youtube-scraper 2>&1 | grep "Comments Worker"
docker logs youtube-scraper 2>&1 | grep "Metrics Refresh"
```

---

## 📈 Monitoring

### Redis Keys

```bash
# Xem tất cả KOLs đang track
docker exec kol-redis redis-cli KEYS "streaming_scores:*"

# Xem chi tiết 1 KOL
docker exec kol-redis redis-cli HGETALL "streaming_scores:mrbeast"

# Xem KOL YouTube
docker exec kol-redis redis-cli HGETALL "kol:youtube:mrbeast"
```

### Kafka Topics

```bash
# Xem messages trong topic
docker exec kol-redpanda rpk topic consume kol.discovery.raw --num 5

# Xem topic stats
docker exec kol-redpanda rpk topic describe kol.profiles.raw
```

### API Quota

Kiểm tra quota usage tại [Google Cloud Console](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas)

---

## 🔄 Flow tổng hợp

### Discovery Flow (Tìm KOL mới)

```
YouTube Trending API
        │
        ▼
┌───────────────────┐
│ youtube_discovery │ ──── mỗi 6h ────▶ kol.discovery.raw
└───────────────────┘                          │
                                               ▼
                                    ┌─────────────────────┐
                                    │ youtube_stats_worker│
                                    │ (resolve by handle) │
                                    └──────────┬──────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              ▼                ▼                ▼
                      kol.profiles.raw  kol.videos.raw  kol.comments.raw
                              │                │                │
                              └────────────────┼────────────────┘
                                               ▼
                                    ┌─────────────────────┐
                                    │   Spark Streaming   │
                                    └──────────┬──────────┘
                                               ▼
                                    ┌─────────────────────┐
                                    │       Redis         │
                                    │ (streaming_scores)  │
                                    └──────────┬──────────┘
                                               ▼
                                    ┌─────────────────────┐
                                    │     Dashboard       │
                                    └─────────────────────┘
```

### Refresh Flow (Cập nhật metrics)

```
┌─────────────────────┐
│   metrics_refresh   │ ──── mỗi 5 phút
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       Redis         │
│ (streaming_scores)  │ ──── đọc username + platform
└──────────┬──────────┘
           │
           ▼
    kol.discovery.raw (event_type="refresh")
           │
           ▼
┌─────────────────────┐
│ youtube_stats_worker│
│ - Resolve handle    │ ◀── Tự động resolve channel_id từ username
│ - Call YouTube API  │
│ - Push to Kafka     │
└──────────┬──────────┘
           │
           ▼
    kol.profiles.raw + kol.videos.raw
           │
           ▼
┌─────────────────────┐
│   Spark Streaming   │
│ - Compute velocity  │ ◀── Tính tốc độ tăng trưởng
│ - Update scores     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       Redis         │
│ (updated scores)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     Dashboard       │
│  (real-time view)   │
└─────────────────────┘
```

---

## ✅ Checklist triển khai

- [ ] Đã có YouTube API Key
- [ ] Đã set environment variables
- [ ] Đã build Docker image
- [ ] Đã start youtube-scraper container
- [ ] Đã verify logs không có errors
- [ ] Đã thấy data trong Kafka topics
- [ ] Đã thấy YouTube KOLs trong Redis
- [ ] Dashboard hiển thị YouTube KOLs

---

## 📝 Notes

1. **Quota Management**: YouTube API có giới hạn 10,000 quota/ngày. Mỗi search tốn 100 quota, nên cần cân nhắc tần suất scrape.

2. **Handle Resolution**: YouTube stats worker có thể tự resolve channel_id từ @handle, không cần lưu channel_id vào Redis như trước.

3. **Platform Separation**: Spark streaming job xử lý cả TikTok và YouTube, phân biệt bằng field `platform`.

4. **Real-time Scores**: Redis key format là `streaming_scores:{username}` với field `platform` để phân biệt.

---

*Last updated: December 9, 2025*

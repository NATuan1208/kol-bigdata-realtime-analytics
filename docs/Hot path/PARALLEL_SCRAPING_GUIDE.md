# 🚀 Hướng Dẫn Chạy Parallel Scraping

## Tổng Quan

Hệ thống scraping TikTok KOL được thiết kế chạy **song song 4 workers** để tối ưu tốc độ:

```
┌─────────────────────────────────────────────────────────────┐
│                    DISCOVERY SCRAPER                        │
│         Tìm KOL mới → Push username lên Kafka              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
              kol.discovery.raw (username)
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  Video   │ │ Comment  │ │ Product  │
   │  Stats   │ │ Extractor│ │ Extractor│
   │  Worker  │ │          │ │          │
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        │            │            │
        ▼            ▼            ▼
   videos.raw   comments.raw  products.raw
        │            │            │
        └────────────┼────────────┘
                     ▼
              ┌──────────────┐
              │ Spark Batch  │
              │ (Bronze →    │
              │  Silver →    │
              │  Gold)       │
              └──────────────┘
```

---

## 📁 Các File Quan Trọng

### Core Files

| File | Mô tả |
|------|-------|
| `ingestion/config.py` | Cấu hình chung (Kafka, Chrome profiles, constants) |
| `ingestion/consumers/base.py` | Base class cho tất cả workers |

### Workers (4 workers chính)

| File | Input Topic | Output Topic | Chức năng |
|------|-------------|--------------|-----------|
| `ingestion/sources/discovery_kol_tiktok.py` | - | `kol.discovery.raw` | Tìm KOL từ TikTok Search/Trending |
| `ingestion/consumers/video_stats_worker.py` | `kol.discovery.raw` | `kol.videos.raw` + `kol.profiles.raw` | Lấy profile + video stats |
| `ingestion/consumers/comment_extractor.py` | `kol.discovery.raw` | `kol.comments.raw` | Lấy comments từ videos |
| `ingestion/consumers/product_extractor.py` | `kol.discovery.raw` | `kol.products.raw` | Lấy products từ videos |

### Scripts

| File | Mô tả |
|------|-------|
| `scripts/start_parallel_scrapers.ps1` | Chạy tất cả workers cùng lúc |
| `scripts/kafka_to_json.py` | Export Kafka messages ra JSON files |

---

## 🛠️ Yêu Cầu

### 1. Python Environment
```powershell
cd E:\Project\kol-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/trainer.txt
```

### 2. Chrome Profiles
Mỗi worker cần 1 Chrome profile riêng (đã login TikTok):

| Worker | Profile |
|--------|---------|
| Discovery | Default |
| Video Stats | video (auto-created) |
| Comment Extractor | comment (auto-created) |
| Product Extractor | product (auto-created) |

> **Note:** Profile được tự động tạo trong `data/chrome_profiles/`. Lần đầu chạy cần login TikTok thủ công.

### 3. Kafka (Redpanda)
```powershell
cd infra
docker compose up -d redpanda redpanda-console
```

Kiểm tra: http://localhost:8080 (Redpanda Console)

---

## 🚀 Cách Chạy

### Option 1: Chạy từng worker (Recommended để test)

**Terminal 1 - Discovery:**
```powershell
.\.venv\Scripts\Activate.ps1
python -m ingestion.sources.discovery_kol_tiktok --mode continuous
```

**Terminal 2 - Video Stats:**
```powershell
.\.venv\Scripts\Activate.ps1
python -m ingestion.consumers.video_stats_worker
```

**Terminal 3 - Comments:**
```powershell
.\.venv\Scripts\Activate.ps1
python -m ingestion.consumers.comment_extractor
```

**Terminal 4 - Products:**
```powershell
.\.venv\Scripts\Activate.ps1
python -m ingestion.consumers.product_extractor
```

### Option 2: Chạy tất cả bằng script
```powershell
.\scripts\start_parallel_scrapers.ps1
```

Với options:
```powershell
# Dry run (không cần Kafka)
.\scripts\start_parallel_scrapers.ps1 -DryRun

# Giới hạn videos
.\scripts\start_parallel_scrapers.ps1 -MaxVideos 10

# Chỉ chạy discovery + video stats
.\scripts\start_parallel_scrapers.ps1 -NoComments -NoProducts
```

---

## 🧪 Test Dry-Run (Không cần Kafka)

Test từng worker mà không cần Kafka chạy:

```powershell
# Test Video Stats Worker
python -m ingestion.consumers.video_stats_worker --dry-run --max-videos 3

# Test Comment Extractor
python -m ingestion.consumers.comment_extractor --dry-run --max-videos 2 --max-comments 10

# Test Product Extractor
python -m ingestion.consumers.product_extractor --dry-run --max-videos 3
```

---

## 📊 Output Data

### Kafka Topics
| Topic | Content |
|-------|---------|
| `kol.discovery.raw` | `{username, source, discovered_at}` |
| `kol.profiles.raw` | `{username, followers, following, likes, bio}` |
| `kol.videos.raw` | `{video_id, username, views, likes, comments, shares}` |
| `kol.comments.raw` | `{video_id, username, comment_text}` |
| `kol.products.raw` | `{product_id, video_id, title, price, sold_count}` |

### Export to JSON
```powershell
python scripts/kafka_to_json.py --topic kol.videos.raw --output data/scrape/videos.json
```

---

## ⚠️ Troubleshooting

### 1. Chrome bị lock
```
selenium.common.exceptions.InvalidArgumentException: user data directory is already in use
```
**Fix:** Đóng tất cả Chrome windows, hoặc kill process:
```powershell
taskkill /F /IM chrome.exe
```

### 2. Kafka connection refused
```
NoBrokersAvailable
```
**Fix:** Chạy Kafka:
```powershell
cd infra
docker compose up -d redpanda
```

### 3. TikTok rate limit
**Fix:** Tăng interval giữa các request trong `config.py`:
```python
SCROLL_PAUSE = 1.5  # Tăng từ 0.5 lên 1.5
```

---

## 📈 Performance

| Metric | Old Flow (Sequential) | New Flow (Parallel) |
|--------|----------------------|---------------------|
| 1 KOL với 20 videos | ~5 min | ~2 min |
| 10 KOLs | ~50 min | ~20 min |
| Throughput | ~2 KOL/10min | ~5 KOL/10min |

---

## 🔧 Cấu Hình

Sửa trong `ingestion/config.py`:

```python
# Số videos tối đa mỗi KOL
MAX_VIDEOS_PER_KOL = 20

# Số comments tối đa mỗi video
MAX_COMMENTS_PER_VIDEO = 50

# Delay giữa các scroll
SCROLL_PAUSE = 0.5

# Kafka broker
DEFAULT_KAFKA_BROKER = "localhost:19092"
```

---

## 📝 Lưu Ý

1. **Chrome Profiles:** Mỗi worker dùng profile riêng, KHÔNG dùng chung
2. **Login TikTok:** Lần đầu chạy mỗi worker, cần login TikTok thủ công
3. **Rate Limiting:** Nếu bị block, tăng `SCROLL_PAUSE` và giảm `MAX_VIDEOS_PER_KOL`
4. **Dry Run:** Luôn test với `--dry-run` trước khi chạy thật
5. **Kafka:** Cần Redpanda chạy trước khi start workers (trừ dry-run mode)

---

## 📞 Support

Nếu gặp vấn đề, check logs trong `data/logs/` hoặc hỏi team.

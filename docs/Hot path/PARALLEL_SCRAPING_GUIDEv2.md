# 🚀 Hướng Dẫn Chạy Parallel Scraping + Real-time Trending

## Tổng Quan

Hệ thống scraping TikTok KOL được thiết kế chạy **song song 5 workers** với **real-time trending score**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         COMPLETE FLOW                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐     ┌──────────────────┐                      │
│  │ DISCOVERY DAEMON │     │ METRICS REFRESH  │                      │
│  │ (mỗi 2-6 tiếng)  │     │ (mỗi 5 phút)     │                      │
│  │ Tìm KOL mới      │     │ Re-push tracked  │                      │
│  └────────┬─────────┘     └────────┬─────────┘                      │
│           │                        │                                │
│           └───────────┬────────────┘                                │
│                       ▼                                             │
│            ┌──────────────────────┐                                 │
│            │  kol.discovery.raw   │                                 │
│            └──────────┬───────────┘                                 │
│                       │                                             │
│       ┌───────────────┼───────────────┐                             │
│       ▼               ▼               ▼                             │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐                        │
│  │ Video   │    │ Comment  │    │ Product  │                        │
│  │ Stats   │    │ Extractor│    │ Extractor│                        │
│  │ Worker  │    │          │    │          │                        │
│  └────┬────┘    └────┬─────┘    └────┬─────┘                        │
│       │              │               │                              │
│       ▼              ▼               ▼                              │
│  kol.videos.raw  comments.raw   products.raw                        │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────┐                       │
│  │         SPARK STREAMING                  │                       │
│  │  (trigger mỗi 30s, tính trending score)  │                       │
│  └────────────────────┬─────────────────────┘                       │
│                       │                                             │
│                       ▼                                             │
│  ┌──────────────────────────────────────────┐                       │
│  │              REDIS                       │                       │
│  │  streaming_scores:{username}             │                       │
│  │  - score, view, like, share              │                       │
│  │  - velocity (tốc độ tăng trưởng)         │                       │
│  └──────────────────────────────────────────┘                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Các File Quan Trọng

### Core Files

| File | Mô tả |
|------|-------|
| `ingestion/config.py` | Cấu hình chung (Kafka, Chrome profiles, constants) |
| `ingestion/consumers/base.py` | Base class cho tất cả workers |

### Workers (5 workers)

| File | Input | Output | Chức năng |
|------|-------|--------|-----------|
| `ingestion/sources/kol_scraper.py` | - | `kol.discovery.raw` | Discovery KOL mới từ TikTok |
| `ingestion/sources/metrics_refresh.py` | Redis | `kol.discovery.raw` | Re-push tracked KOLs để tính velocity |
| `ingestion/consumers/video_stats_worker.py` | `kol.discovery.raw` | `kol.videos.raw` + `kol.profiles.raw` | Lấy profile + video stats |
| `ingestion/consumers/comment_extractor.py` | `kol.discovery.raw` | `kol.comments.raw` | Lấy comments từ videos |
| `ingestion/consumers/product_extractor.py` | `kol.discovery.raw` | `kol.products.raw` | Lấy products từ videos |

### Streaming Jobs

| File | Mô tả |
|------|-------|
| `streaming/spark_jobs/kafka_trending_stream.py` | Tính trending score real-time từ Kafka → Redis |

### Scripts

| File | Mô tả |
|------|-------|
| `scripts/start_full_platform.ps1` | **One-click start** toàn bộ platform |
| `scripts/start_parallel_scrapers.ps1` | Chạy tất cả workers song song |
| `scripts/kafka_to_json.py` | Export Kafka messages ra JSON files |

---

## 🛠️ Setup Infrastructure

### 1. Prerequisites

```powershell
# Python 3.10+ 
# Google Chrome (bản mới nhất)
# Docker Desktop

# Setup Python environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/trainer.txt
pip install selenium webdriver-manager kafka-python redis
```

### 2. Start Docker Containers

```powershell
cd infra
docker-compose up -d
```

**Containers cần chạy:**
- `kol-redpanda` (Kafka) - port 19092
- `kol-redis` - port 16379
- `kol-spark-master` - port 8084 (UI)
- `kol-spark-worker-1`, `kol-spark-worker-2`

### 3. Setup Redis trong Spark Container

```powershell
# Cài redis package trong Spark containers (chạy 1 lần)
docker exec -u root kol-spark-master pip install redis
docker exec -u root infra-spark-worker-1 pip install redis
docker exec -u root infra-spark-worker-2 pip install redis

# Verify
docker exec kol-spark-master python3 -c "import redis; print('redis OK')"
```

### 4. Setup Spark Ivy Cache (nếu gặp permission error)

```powershell
# Fix permission cho Ivy cache
docker exec -u root kol-spark-master mkdir -p /home/spark/.ivy2
docker exec -u root kol-spark-master chmod -R 777 /home/spark/.ivy2
```

---

## 🚀 Cách Chạy

### Option 1: One-Click Start (Recommended)

```powershell
# Start toàn bộ platform
.\scripts\start_full_platform.ps1

# Với options
.\scripts\start_full_platform.ps1 -NoComments -NoProducts -MaxKols 10
```

Script sẽ:
1. ✅ Check infrastructure (Redis, Kafka, Spark)
2. ✅ Start Spark Streaming job
3. ✅ Start Discovery Daemon
4. ✅ Start Video/Comment/Product Workers (delay 240s)
5. ✅ Start Metrics Refresh

### Option 2: Chạy từng component

**Terminal 1 - Start Spark Streaming:**
```powershell
docker exec -d kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 `
    /opt/spark-jobs/kafka_trending_stream.py
```

**Terminal 2 - Discovery:**
```powershell
py -m ingestion.sources.kol_scraper daemon --discovery-only --interval 7200
```

**Terminal 3 - Video Stats:**
```powershell
py -m ingestion.consumers.video_stats_worker --max-videos 20 --start-delay 240
```

**Terminal 4 - Metrics Refresh:**
```powershell
py -m ingestion.sources.metrics_refresh --interval 300
```

---

## ⚙️ Configuration

### Intervals

| Parameter | Default | Mô tả |
|-----------|---------|-------|
| `DiscoveryInterval` | 7200s (2h) | Tần suất tìm KOL mới |
| `RefreshInterval` | 300s (5min) | Tần suất re-push để tính velocity |
| `WorkerDelay` | 240s (4min) | Workers đợi Discovery push messages |

### Limits

| Parameter | Default | Mô tả |
|-----------|---------|-------|
| `MaxKols` | 20 | Số KOL mới mỗi lần discovery |
| `MaxVideos` | 20 | Số videos scrape mỗi KOL |
| `MaxComments` | 50 | Số comments mỗi video |
| `MaxTrackedKols` | 150 | Giới hạn KOL được track |

### Trending Score Formula

```
score = ALPHA * view_velocity + BETA * like_velocity + GAMMA * share_velocity

# Defaults:
ALPHA = 1.0   # View weight
BETA = 0.5    # Like weight  
GAMMA = 0.2   # Share weight

# Velocity = current - previous (delta giữa 2 lần scrape)
```

---

## 📊 Monitoring

### Check Spark Job

```powershell
# Spark UI
http://localhost:8084

# Check running apps
docker exec kol-spark-master curl -s http://localhost:8080/json/ | Select-String "KOL-Trending"
```

### Check Redis Trending Scores

```powershell
# List all tracked KOLs
docker exec kol-redis redis-cli KEYS "streaming_scores:*"

# Get score for specific KOL
docker exec kol-redis redis-cli HGETALL "streaming_scores:xuannhilamgido"
```

### Check Kafka Topics

```powershell
# List topics
docker exec kol-redpanda rpk topic list

# View recent messages
docker exec kol-redpanda rpk topic consume kol.videos.raw --num 5 -f "%v\n"
```

---

## 🔄 Trending Flow Explained

```
┌─────────────────────────────────────────────────────────────────────┐
│  VELOCITY-BASED TRENDING                                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  T=0:    Discovery tìm @kol_A (mới)                                 │
│          VideoStatsWorker scrape: likes=1000                        │
│          Spark: velocity=1000 (lần đầu = absolute)                  │
│          Redis: score=500 (0.5 * 1000)                              │
│                                                                     │
│  T=5min: Metrics Refresh re-push @kol_A                             │
│          VideoStatsWorker scrape lại: likes=1200                    │
│          Spark: velocity=200 (1200-1000)                            │
│          Redis: score=100 (0.5 * 200)                               │
│                                                                     │
│  T=10min: Metrics Refresh re-push @kol_A                            │
│           VideoStatsWorker scrape lại: likes=2000                   │
│           Spark: velocity=800 (2000-1200)                           │
│           Redis: score=400 (0.5 * 800) ← TRENDING UP! 🔥            │
│                                                                     │
│  → KOL có velocity cao = đang trending                              │
│  → KOL có velocity thấp/0 = không trending                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Troubleshooting

### 1. Spark job không start

```powershell
# Check logs
docker logs kol-spark-master --tail 100

# Verify Kafka connector
docker exec kol-spark-master ls /home/spark/.ivy2/jars/ | Select-String "kafka"
```

### 2. Redis không có data

```powershell
# Check Spark job đang chạy
docker exec kol-spark-master curl -s http://localhost:8080/json/ | Select-String "activeapps"

# Check Kafka có messages
docker exec kol-redpanda rpk topic consume kol.videos.raw --num 1
```

### 3. Workers không nhận messages

```powershell
# Reset offset về latest
docker exec kol-redpanda rpk group seek kol-video-stats-v3 --to end

# Check consumer group
docker exec kol-redpanda rpk group describe kol-video-stats-v3
```

### 4. Chrome bị lock

```powershell
taskkill /F /IM chrome.exe
```

---

## 📈 Performance

| Metric | Value |
|--------|-------|
| Discovery | 20-30 KOL / lần |
| Video scrape | 1-2 min / KOL |
| Spark trigger | 30 giây |
| Redis TTL | 1 giờ |
| End-to-end latency | ~2-5 phút |

---

## 📝 Lưu Ý Quan Trọng

1. **Worker Delay**: Workers cần delay 240s để đợi Discovery push messages trước
2. **Discovery vs Refresh**: 
   - Discovery: 2-6 tiếng/lần (tìm KOL mới)
   - Refresh: 5 phút/lần (tính velocity cho KOL đã track)
3. **Redis trong Spark**: Phải cài `redis` package trong tất cả Spark containers
4. **startingOffsets**: Dùng `latest` cho production, `earliest` cho backfill
5. **Rate Limiting**: TikTok rate limit strict, cần delay giữa requests

---

## 📞 Support

- Logs: `data/logs/`
- Spark UI: http://localhost:8084
- Kafka Console: http://localhost:8080

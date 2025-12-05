# 📊 KOL Analytics Platform - Progress Report

> **Ngày cập nhật:** 30/11/2025  
> **Giai đoạn:** Phase 1 - Data Ingestion & Infrastructure

---

## 🎯 Tổng quan dự án

**KOL Analytics Platform** là hệ thống phân tích KOL (Key Opinion Leaders) trên các nền tảng mạng xã hội, tập trung vào:
- Phát hiện KOL tiềm năng (Discovery)
- Thu thập dữ liệu profile, videos, comments, products
- Phân tích hiệu quả bán hàng qua TikTok Shop
- Dự đoán KOL có tiềm năng viral

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Scraping** | Selenium + Chrome Profile (Stealth) |
| **Message Queue** | Redpanda (Kafka-compatible) |
| **Stream Processing** | Apache Spark 3.5 (Lambda Architecture) |
| **Data Lake** | Apache Iceberg on MinIO (S3) |
| **Storage** | MinIO (Bronze/Silver/Gold layers) |
| **Orchestration** | Docker Compose |

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAMBDA ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐     ┌───────────┐     ┌────────────────────────┐  │
│  │ TikTok  │────▶│ Redpanda  │────▶│  BATCH LAYER (Cold)    │  │
│  │ Scraper │     │  (Kafka)  │     │  kafka_to_iceberg      │  │
│  └─────────┘     └─────┬─────┘     │  _simple.py            │  │
│                        │           │  (Reprocess all)        │  │
│                        │           └────────────┬───────────┘  │
│                        │                        │              │
│                        │           ┌────────────▼───────────┐  │
│                        └──────────▶│  SPEED LAYER (Hot)     │  │
│                                    │  kafka_to_iceberg      │  │
│                                    │  _streaming.py         │  │
│                                    │  (Real-time, 30s)      │  │
│                                    └────────────┬───────────┘  │
│                                                 │              │
│                                    ┌────────────▼───────────┐  │
│                                    │  Apache Iceberg        │  │
│                                    │  (MinIO S3 Storage)    │  │
│                                    │  Bronze → Silver → Gold │  │
│                                    └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ Những gì đã hoàn thành

### 1. TikTok Scraper (`kol_scraper.py`)

#### Các tính năng đã implement:

| Feature | Status | Mô tả |
|---------|--------|-------|
| **Discovery Mode** | ✅ Done | Tìm KOL mới từ Search & FYP |
| **Profile Scraping** | ✅ Done | Lấy followers, bio, verified status |
| **Video Scraping** | ✅ Done | Lấy views, likes, comments, shares |
| **Comment Scraping** | ✅ Done | Scroll và extract comments (cho phoBERT) |
| **Product Scraping** | ✅ Done | Extract từ video JSON, lấy `sold_count` |
| **Daemon Mode** | ✅ Done | Chạy liên tục với interval |
| **Kafka Integration** | ✅ Done | Push real-time lên Redpanda |

#### Kết quả scraping (29/11/2025):

```
📊 KAFKA TOPICS DATA:
├── kol.discovery.raw    : 1,153 records
├── kol.profiles.raw     : 28 records  
├── kol.videos.raw       : 53 records
├── kol.comments.raw     : 666 records
└── kol.products.raw     : 8 records (với sold_count lên đến 78,100+)
```

#### Các vấn đề đã giải quyết:

| Vấn đề | Giải pháp |
|--------|-----------|
| TikTok block headless Chrome | Dùng `--start-minimized` thay vì `--headless` |
| TikTok block Docker container | Chạy trên Windows host với Chrome Profile |
| Video chiếm full screen, không thấy comments | Bỏ `Emulation.setDeviceMetricsOverride`, fix window size 1400x900 |
| Regex không match JSON mới của TikTok | Update pattern để match các attributes mới |
| Captcha/Verify | Dùng Chrome Profile để giữ session |

### 2. Kafka Infrastructure (Redpanda)

```yaml
Services running:
├── kol-redpanda         : localhost:19092 (Kafka API)
├── kol-redpanda-console : localhost:8080 (Web UI)
```

**Kafka Topics:**
- `kol.discovery.raw` - Raw discovery events
- `kol.profiles.raw` - Raw profile data
- `kol.videos.raw` - Raw video stats
- `kol.comments.raw` - Raw comments (for NLP/spam detection)
- `kol.products.raw` - Raw product data with sales metrics

### 3. Spark ETL Pipeline

#### A. Batch Job (`kafka_to_iceberg_simple.py`) - ✅ Working

```
Flow: Kafka → Spark Batch (chạy 1 lần) → Iceberg (MinIO)

📥 Loaded to Iceberg:
├── kol.bronze.discovery : 1,153 rows
├── kol.bronze.profiles  : 28 rows
├── kol.bronze.videos    : 53 rows
├── kol.bronze.comments  : 666 rows
└── kol.bronze.products  : 8 rows
```

**Khi nào dùng Batch:**
- Reprocess toàn bộ data
- Initial load từ Kafka
- Scheduled jobs (Airflow)

#### B. Streaming Job (`kafka_to_iceberg_streaming.py`) - 🆕 New

```
Flow: Kafka → Spark Streaming (chạy 24/7) → Iceberg (near real-time)

Trigger: Mỗi 30 giây process 1 micro-batch
```

**Khi nào dùng Streaming:**
- Real-time dashboard
- Near real-time analytics
- Continuous data ingestion

**Iceberg Tables Location:** `s3a://kol-bronze/iceberg/bronze/`

### 4. Storage (MinIO)

```
MinIO Buckets:
├── kol-bronze/   ← Raw data (Iceberg tables)
├── kol-silver/   ← Cleaned & transformed
├── kol-gold/     ← Aggregated for analytics
└── kol-mlflow/   ← ML model artifacts
```

**Credentials:** `minio` / `minio123`

---

## 🚧 Đang phát triển / Cần làm tiếp

### 1. Spark Streaming Mode (Priority: HIGH)

**Hiện tại:** Batch job chạy 1 lần, load hết data rồi stop.

**Cần làm:** Chuyển sang Streaming mode để:
- Spark chạy 24/7
- Tự động consume Kafka khi có data mới
- Real-time write vào Iceberg

```python
# Streaming approach (cần implement)
df = spark.readStream \
    .format("kafka") \
    .option("subscribe", "kol.discovery.raw") \
    .load()

df.writeStream \
    .format("iceberg") \
    .option("checkpointLocation", "/checkpoints/discovery") \
    .toTable("kol.bronze.discovery")
```

~~**Lưu ý:** Iceberg + Spark Streaming cần config đặc biệt cho ACID writes.~~ ✅ **ĐÃ IMPLEMENT!**

### Lambda Architecture - ✅ IMPLEMENTED

**Batch Layer (Cold Path):**
```
Kafka → spark_jobs/kafka_to_iceberg_simple.py → Iceberg
       (chạy 1 lần, reprocess toàn bộ)
```

**Speed Layer (Hot Path):**
```
Kafka → streaming/kafka_to_iceberg_streaming.py → Iceberg
       (chạy 24/7, micro-batch 30s)
```

**Cách chạy Lambda Pipeline:**
```powershell
# Cách 1: Chạy script
.\scripts\start_lambda_pipeline.ps1

# Cách 2: Chạy manual
# Terminal 1 - Spark Streaming (hot path)
docker exec kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.0 `
    /opt/spark-jobs/kafka_to_iceberg_streaming.py

# Terminal 2 - Scraper daemon
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon
```

**Tại sao dùng Lambda Architecture?**
| Layer | Latency | Use Case |
|-------|---------|----------|
| Batch | Minutes-Hours | Historical reprocessing, backfill |
| Speed | Seconds | Real-time dashboards, alerts |

### 2. Twitter/X Scraper (Priority: MEDIUM)

**Độ khó:** Trung bình (dễ hơn TikTok)

| Aspect | TikTok | Twitter |
|--------|--------|---------|
| Headless | ❌ Blocked | ✅ OK |
| Captcha | 🔴 Thường xuyên | 🟢 Hiếm |
| Login required | 🟡 Một phần | 🟢 Không (public) |
| API | ❌ Không có free | 🟡 $100/tháng hoặc scrape |

**Options:**
1. **Scraping trực tiếp** - Dùng Selenium/Playwright, headless OK
2. **Nitter** - Frontend thay thế, nhưng unstable
3. **Twitter API** - $100/tháng (Basic tier)

### 3. YouTube Scraper (Priority: MEDIUM)

**Độ khó:** Dễ nhất! 🟢

```python
# YouTube Data API v3 - MIỄN PHÍ
# Quota: 10,000 units/ngày (~100-500 requests)

from googleapiclient.discovery import build

youtube = build('youtube', 'v3', developerKey='API_KEY')

# Search channels
response = youtube.search().list(
    q='review mỹ phẩm',
    type='channel',
    maxResults=50
).execute()

# Get channel stats
channel = youtube.channels().list(
    id='UC...',
    part='statistics,snippet'
).execute()
```

**Cần làm:**
1. Tạo Google Cloud project
2. Enable YouTube Data API v3
3. Tạo API key
4. Implement scraper tương tự TikTok

### 4. Airflow Scheduling (Priority: LOW)

Nếu dùng Batch mode thay vì Streaming, cần schedule jobs:

```
Airflow DAG:
├── scraper_dag (mỗi 30 phút)
│   └── run TikTok scraper daemon 1 round
├── etl_dag (mỗi 10 phút)  
│   └── run Spark batch job
└── ml_dag (mỗi ngày)
    └── train/update models
```

---

## 🤔 Những điểm đang phân vân

### 1. Streaming vs Batch cho Spark?

| Mode | Pros | Cons |
|------|------|------|
| **Streaming** | Real-time, tự động | Phức tạp hơn, tốn resource |
| **Batch + Airflow** | Đơn giản, dễ debug | Delay 5-10 phút |

**Recommendation:** Start với Batch + Airflow, migrate sang Streaming khi cần real-time.

### 2. TikTok Automation 24/7?

**Vấn đề:** TikTok bắt verify theo chu kỳ, không thể 100% tự động.

**Options:**
1. **Telegram Alert** - Khi bị block, gửi notification → verify manual
2. **Multiple Chrome Profiles** - Rotate profiles để giảm verify
3. **Reduce frequency** - Scrape mỗi 30-60 phút thay vì 5 phút

### 3. Hive Metastore vs Hadoop Catalog?

**Hiện tại:** Dùng Hadoop Catalog (đơn giản, không cần Hive Metastore)

**Sau này:** Nếu cần query từ Trino/Presto, nên setup Hive Metastore

---

## 📁 Cấu trúc files quan trọng

```
kol-platform/
├── ingestion/sources/
│   ├── kol_scraper.py          # Main TikTok scraper
│   ├── scraper_utils.py        # WebDriver setup, Kafka helpers
│   └── kol_scraper_playwright.py # Alternative (Playwright)
│
├── streaming/spark_jobs/
│   ├── kafka_to_iceberg_simple.py  # Batch ETL (đang dùng)
│   └── kol_kafka_to_iceberg.py     # Streaming ETL (cần hoàn thiện)
│
├── scripts/
│   └── kafka_to_json.py        # Export Kafka → JSON (debug)
│
├── infra/
│   ├── docker-compose.kol.yml  # KOL services (Spark, Redpanda, etc.)
│   └── docker-compose.base.yml # Base services (MinIO, Postgres)
│
├── data/
│   ├── chrome_profile/         # Chrome session for TikTok
│   ├── kafka_export/           # Exported JSON from Kafka
│   └── scrape/                 # Checkpoint files
│
└── docs/
    └── PROJECT_PROGRESS_REPORT.md  # This file
```

---

## 🚀 Roadmap tiếp theo

### Week 1: Hoàn thiện Data Pipeline
- [ ] Setup Spark Streaming mode
- [ ] Test end-to-end: Scraper → Kafka → Spark → Iceberg
- [ ] Setup Trino để query Iceberg tables

### Week 2: Expand Data Sources
- [ ] Implement YouTube scraper (API-based)
- [ ] Implement Twitter scraper (Selenium-based)
- [ ] Unified schema cho multi-platform

### Week 3: Analytics & ML
- [ ] Bronze → Silver transformation (clean, dedupe)
- [ ] Silver → Gold aggregation (KOL metrics, rankings)
- [ ] phoBERT spam detection trên comments
- [ ] KOL scoring model (engagement, growth, trust)

### Week 4: Dashboard & API
- [ ] FastAPI endpoints cho KOL data
- [ ] Grafana dashboard cho monitoring
- [ ] Basic web UI cho KOL discovery

---

## 📞 Commands hay dùng

### Start Infrastructure
```powershell
cd e:\Project\kol-platform\infra
docker-compose -f docker-compose.kol.yml up -d
```

### Run TikTok Scraper (Discovery)
```powershell
cd e:\Project\kol-platform
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper discovery --niche "beauty,fashion" --headless
```

### Run Spark ETL (Batch)
```powershell
docker exec kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    /opt/spark-jobs/kafka_to_iceberg_simple.py
```

### Check Kafka Data
```powershell
.\.venv\Scripts\python.exe scripts/kafka_to_json.py
```

### View MinIO Console
```
http://localhost:9001
Login: minio / minio123
```

### View Spark UI
```
http://localhost:8084
```

### View Redpanda Console
```
http://localhost:8080
```

---

## 📝 Notes

- **Chrome Profile Path:** `data/chrome_profile/` - Cần verify TikTok 1 lần, sau đó session được lưu
- **TikTok Headless:** KHÔNG dùng `--headless`, dùng `--start-minimized` để tránh bị detect
- **MinIO Credentials:** `minio` / `minio123` (khác với default `minioadmin`)
- **Kafka Bootstrap:** `localhost:19092` (external) hoặc `redpanda:9092` (internal Docker)

---

*Report này được tạo để track progress và chia sẻ với team. Update thường xuyên khi có tiến triển mới.*

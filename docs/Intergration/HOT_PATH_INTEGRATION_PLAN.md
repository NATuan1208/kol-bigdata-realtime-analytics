# 🔥 Hot Path Integration Plan

> **Ngày lập:** 03/12/2025  
> **Trạng thái:** ✅ IMPLEMENTED (Batch Mode Working)

---

## 🎉 Kết Quả Đã Đạt Được

### ✅ Hot Path Scoring Pipeline Hoạt Động

```
Flow đã test thành công:
Kafka (kol.profiles.raw) 
    → Spark Structured Streaming 
    → Parse JSON (support raw strings: "11.3K", "1.3M")
    → Call Trust API (http://api:8080/predict/trust)
    → Output to Kafka (scores.stream)
    → Cache to Redis (optional)

KPIs:
- 58 profiles processed in batch mode
- Trust Score output: 88-89 range (low risk)
- Latency: 44-67ms per API call
- Model version: trust-score-lightgbm-optuna-Production
```

### 📤 Sample Output (scores.stream topic)

```json
{
  "kol_id": "littlemheart",
  "platform": "tiktok", 
  "timestamp": "2025-12-03 03:34:00.634346",
  "trust_score": 88.75,
  "trust_label": "low",
  "trust_confidence": 0.8875,
  "latency_ms": 44,
  "model_version_trust": "trust-score-lightgbm-optuna-Production"
}
```

---

## 📊 Tổng quan Hạ tầng Hiện tại

### ✅ Services Đang Chạy

| Service | Container | Port | Status |
|---------|-----------|------|--------|
| **Redpanda (Kafka)** | kol-redpanda | 19092 (external) | ✅ Healthy |
| **Spark Master** | kol-spark-master | 7077, 8084 (UI) | ✅ Healthy |
| **Spark Workers** | infra-spark-worker-1/2 | - | ✅ Running |
| **Spark Streaming** | kol-spark-streaming | - | ✅ Ready (idle) |
| **Spark History** | kol-spark-history | 18080 | ✅ Running |
| **MLflow** | kol-mlflow | 5000 | ✅ Running |
| **MinIO (S3)** | sme-minio | 9000-9001 | ✅ Healthy |
| **API** | kol-api | 8000 | ✅ Healthy (code cũ) |
| **Trino** | sme-trino | 8081 | ✅ Healthy |

### 📨 Kafka Topics Có Sẵn

```
INPUT TOPICS (từ Scraper):
├── kol.discovery.raw   (3 partitions) - KOL mới phát hiện
├── kol.profiles.raw    (3 partitions) - Profile data
├── kol.videos.raw      (3 partitions) - Video stats
├── kol.comments.raw    (3 partitions) - Comments
└── kol.products.raw    (3 partitions) - Product data

STREAMING TOPICS (cho Hot Path):
├── events.social.raw   (6 partitions) - Social events
├── events.web.raw      (6 partitions) - Web tracking
├── events.tx.raw       (6 partitions) - Transactions
├── features.stream     (4 partitions) - Feature output
├── alerts.stream       (2 partitions) - Alerts
└── metrics.windowed    (4 partitions) - Windowed metrics
```

### 🔗 API Endpoints Hiện tại (Container)

```
✅ GET  /healthz                    - Health check
✅ GET  /kol/{kol_id}/trust         - Get trust score
✅ GET  /forecast/{kol_id}          - Forecast
✅ POST /predict/trust              - Trust score prediction
✅ POST /predict/trust/batch        - Batch trust prediction
✅ POST /predict/trust/features     - Prediction from features
✅ GET  /predict/trust/model-info   - Model info
```

**⚠️ CHƯA CÓ:** `/predict/success`, `/predict/trending` (đã code local, chưa deploy)

---

## 🎯 Kiến trúc Hot Path Mục tiêu

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           HOT PATH FLOW                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [TikTok Scraper]                                                        │
│        │                                                                 │
│        ▼                                                                 │
│  ┌─────────────┐                                                         │
│  │  Redpanda   │ ◄── kol.profiles.raw, kol.videos.raw                   │
│  │  (Kafka)    │                                                         │
│  └──────┬──────┘                                                         │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              SPARK STRUCTURED STREAMING                           │   │
│  │  ┌────────────────┐    ┌─────────────────┐    ┌──────────────┐   │   │
│  │  │ 1. Parse JSON  │───►│ 2. Extract      │───►│ 3. Call API  │   │   │
│  │  │    from Kafka  │    │    Features     │    │    /predict  │   │   │
│  │  └────────────────┘    └─────────────────┘    └──────┬───────┘   │   │
│  └──────────────────────────────────────────────────────┼───────────┘   │
│                                                          │               │
│         ┌────────────────────────────────────────────────┘               │
│         │                                                                │
│         ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    OUTPUT SINKS                                   │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │    │
│  │  │ Kafka Topic  │  │   Redis      │  │  Cassandra   │           │    │
│  │  │ scores.stream│  │  (Cache)     │  │ (Time-series)│           │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Kế hoạch Implementation

### Phase 1: Chuẩn bị API (1-2 giờ)

| Task | Mô tả | File |
|------|-------|------|
| 1.1 | Rebuild API container với code mới | `Dockerfile.api` |
| 1.2 | Verify endpoints: /predict/trust, /predict/success, /predict/trending | Test |
| 1.3 | Thêm combined endpoint `/predict/kol-score` trả 3 scores | `predict.py` |

### Phase 2: Implement Hot Path Scoring Job (2-3 giờ)

| Task | Mô tả | File |
|------|-------|------|
| 2.1 | Tạo Spark job đọc từ kol.profiles.raw | `hot_path_scoring.py` |
| 2.2 | Parse JSON và extract features | `hot_path_scoring.py` |
| 2.3 | Gọi HTTP API /predict/kol-score | `hot_path_scoring.py` |
| 2.4 | Write kết quả ra Kafka topic `scores.stream` | `hot_path_scoring.py` |
| 2.5 | Write vào Redis cache | `hot_path_scoring.py` |

### Phase 3: Testing & Integration (1-2 giờ)

| Task | Mô tả | Tool |
|------|-------|------|
| 3.1 | Push test data vào Kafka | rpk / Python producer |
| 3.2 | Submit Spark job | spark-submit |
| 3.3 | Verify output trong Kafka & Redis | rpk consume / redis-cli |
| 3.4 | Monitor Spark UI | http://localhost:8084 |

---

## 🛠️ Technical Details

### Input Schema (kol.profiles.raw)

```json
{
  "event_id": "uuid",
  "event_time": "2025-12-03T10:00:00Z",
  "event_type": "profile",
  "platform": "tiktok",
  "username": "user123",
  "followers_count": 50000,
  "following_count": 500,
  "post_count": 200,
  "favorites_count": 10000,
  "verified": false,
  "bio": "Content creator",
  "profile_url": "https://..."
}
```

### Output Schema (scores.stream)

```json
{
  "kol_id": "user123",
  "platform": "tiktok",
  "timestamp": "2025-12-03T10:00:05Z",
  "scores": {
    "trust_score": 75.5,
    "trust_label": "Moderate",
    "success_score": 65.2,
    "success_label": "High",
    "trending_score": 82.1,
    "trending_label": "Viral"
  },
  "latency_ms": 45,
  "model_versions": {
    "trust": "lgbm-optuna-v1",
    "success": "lgbm-binary-v2",
    "trending": "formula-v2"
  }
}
```

### API Combined Endpoint Spec

```python
POST /predict/kol-score

Request:
{
  "kol_id": "user123",
  "followers_count": 50000,
  "following_count": 500,
  "post_count": 200,
  "favorites_count": 10000,
  "account_age_days": 365,
  "verified": false,
  "has_bio": true,
  "has_url": false,
  "has_profile_image": true,
  "bio_length": 50,
  # Additional for success/trending
  "avg_views": 10000,
  "avg_likes": 500,
  "avg_comments": 50,
  "avg_shares": 20,
  "total_videos": 200,
  "video_count_30d": 15,
  "growth_rate": 0.05
}

Response:
{
  "kol_id": "user123",
  "trust": { "score": 75.5, "label": "Moderate", "confidence": 0.82 },
  "success": { "score": 65.2, "label": "High", "confidence": 0.65 },
  "trending": { "score": 82.1, "label": "Viral", "growth": 3.5 },
  "model_versions": {...},
  "processing_time_ms": 45
}
```

---

## 🚀 Quick Start Commands

### 1. Kiểm tra hạ tầng

```powershell
# Check containers
docker ps --format "table {{.Names}}\t{{.Status}}" | Select-String "spark|redpanda|api|mlflow"

# Check Kafka topics
docker exec kol-redpanda rpk topic list

# Check API health
curl http://localhost:8000/healthz
```

### 2. Rebuild API với code mới

```powershell
cd dwh/infra
docker compose -f docker-compose.kol.yml build api
docker compose -f docker-compose.kol.yml up -d api
```

### 3. Submit Spark Streaming Job

```powershell
docker exec kol-spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
  /opt/spark-jobs/hot_path_scoring.py
```

### 4. Test với sample data

```powershell
# Push test profile
docker exec kol-redpanda rpk topic produce kol.profiles.raw --brokers localhost:9092

# Consume scores
docker exec kol-redpanda rpk topic consume scores.stream --brokers localhost:9092
```

---

## 📈 Success Metrics

| Metric | Target | Hiện tại |
|--------|--------|----------|
| End-to-end latency | < 5s | TBD |
| Throughput | > 100 events/s | TBD |
| API response time | < 200ms | ~50ms |
| Uptime | 99.9% | TBD |

---

## ⚠️ Known Issues & Mitigations

| Issue | Impact | Mitigation |
|-------|--------|------------|
| API container chạy code cũ | Không có /predict/success, /trending | Rebuild container |
| Spark packages cần download | Lần đầu chạy chậm | Pre-download packages |
| Cassandra/Redis chưa init schema | Write fail | Tạo init scripts |
| Network latency API call | Tăng latency | Batch API calls |

---

## 📅 Timeline

| Day | Task | Owner |
|-----|------|-------|
| Day 1 | Phase 1: API preparation | Dev |
| Day 1-2 | Phase 2: Spark job implementation | Dev |
| Day 2 | Phase 3: Integration testing | Dev |
| Day 3 | Documentation & demo | Dev |

---

## 🔗 References

- [Spark Structured Streaming](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
- [Kafka Spark Integration](https://spark.apache.org/docs/latest/structured-streaming-kafka-integration.html)
- [Project Progress Report](./Hot%20path/PROJECT_PROGRESS_REPORT.md)
- [Lakehouse Integration Report](./LAKEHOUSE_INTEGRATION_REPORT.md) ← **NEW: Cold Path + Lakehouse Architecture**

# Unified Hot Path Scoring - Architecture Documentation

## Overview

Hot Path trong KOL Platform tích hợp **3 loại scoring** vào một Spark Streaming pipeline:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        UNIFIED HOT PATH                                 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    Kafka Topics                  Spark Streaming                        │
│    ────────────                  ───────────────                        │
│                                                                         │
│   ┌─────────────────┐         ┌──────────────────┐                      │
│   │ kol.profiles.raw│────────►│  Trust Score UDF │──┐                   │
│   │  (followers,    │         │  (rule-based)    │  │                   │
│   │   verified)     │         └──────────────────┘  │                   │
│   └─────────────────┘                               │                   │
│                                                      │   ┌────────────┐ │
│   ┌─────────────────┐         ┌──────────────────┐  ├──►│ COMPOSITE  │ │
│   │ kol.videos.raw  │────────►│Trending Score UDF│──┤   │  SCORE     │ │
│   │  (views, likes, │         │  (velocity)      │  │   │            │ │
│   │   event_count)  │         └──────────────────┘  │   │ Weights:   │ │
│   └─────────────────┘                               │   │ T=0.4      │ │
│                                                      │   │ S=0.35    │ │
│   ┌─────────────────┐         ┌──────────────────┐  │   │ Tr=0.25   │ │
│   │kol.products.raw │────────►│Success Score UDF │──┘   └────────────┘ │
│   │  (engagement,   │         │  (LightGBM/rules)│                │     │
│   │   sold_count)   │         └──────────────────┘                │     │
│   └─────────────────┘                                             ▼     │
│                                                         ┌───────────────┐
│                                                         │   REDIS ONLY  │
│                                                         │ ─────────────│
│                                                         │ Hash: scores │
│                                                         │ ZSet: ranking│
│                                                         │      ↓       │
│                                                         │   API → UI   │
│                                                         └───────────────┘
└────────────────────────────────────────────────────────────────────────┘
```

## Why Redis Only (No Kafka Output)?

**Câu hỏi**: Tại sao không output ra Kafka topic `scores.stream`?

**Trả lời**: Kafka output **KHÔNG CẦN THIẾT** cho use case này vì:

| Kafka Output | Redis Output |
|-------------|--------------|
| Cần khi có multi-consumer | ✅ Single consumer (API) |
| Cần cho audit/replay | ❌ Không cần replay scores |
| Thêm latency | ✅ Direct write nhanh hơn |
| Duplicate storage | ✅ Redis là single source of truth |

**Flow đúng:**
```
Kafka (raw data) → Spark → Redis → API → UI
        INPUT              OUTPUT    QUERY
```

## 3 Scoring Models

### 1. Trending Score (Velocity-based)

**Source**: `models/trending/trending_score_v2.py`
**Input Topic**: `kol.videos.raw`, `kol.discovery.raw`
**Algorithm**: Velocity-based with time decay

```python
# Formula
raw_score = α * personal_growth + β * market_position + γ * momentum

# Where:
# - personal_growth = current_velocity / baseline_velocity
# - market_position = current_velocity / global_avg
# - momentum = (current - previous) / previous
# - α=0.5, β=0.3, γ=0.2

# Normalization (Sigmoid)
trending_score = 100 / (1 + exp(-k * (raw_score - threshold)))
# k=0.8, threshold=2.0
```

**Labels**:
| Score Range | Label |
|------------|-------|
| ≥ 80 | Viral |
| ≥ 60 | Hot |
| ≥ 40 | Warm |
| ≥ 25 | Normal |
| < 25 | Cold |

### 2. Success Score (LightGBM)

**Source**: `models/success/train_success_score_v2.py`
**Input Topic**: `kol.products.raw`
**Algorithm**: LightGBM binary classification (High vs Not-High)

**Features used**:
- `video_views`, `video_likes`, `video_comments`, `video_shares`
- `engagement_rate`, `engagement_total`
- `est_clicks`, `est_ctr`
- Derived: `likes_per_view`, `comments_per_view`, `log_views`, `log_engagement`

**Fallback**: Rule-based scoring when model unavailable

```python
# Rule-based fallback weights
score = (
    views_component * 0.30 +      # 30 pts
    engagement_rate * 0.30 +       # 30 pts
    ctr_component * 0.20 +         # 20 pts
    interaction_quality * 0.20     # 20 pts
)
```

**Labels**:
| Score Range | Label |
|------------|-------|
| ≥ 70 | High |
| ≥ 40 | Medium |
| < 40 | Low |

### 3. Trust Score (Rule-based)

**Source**: `streaming/spark_jobs/unified_hot_path.py`
**Input Topic**: `kol.profiles.raw`
**Algorithm**: Multi-factor rule-based

**Components** (100 points total):
| Component | Points | Logic |
|-----------|--------|-------|
| Follower/Following ratio | 25 | ratio ≥10 = 25pts, ≥5 = 20pts, ... |
| Follower count tier | 25 | ≥1M = 25pts, ≥100K = 22pts, ... |
| Post activity | 20 | ≥100 posts = 20pts, ... |
| Engagement authenticity | 20 | Actual vs expected engagement |
| Verified bonus | 10 | +10 if verified |

**Labels**:
| Score Range | Label |
|------------|-------|
| ≥ 80 | Highly Trustworthy |
| ≥ 60 | Trustworthy |
| ≥ 40 | Moderate |
| ≥ 25 | Low Trust |
| < 25 | Suspicious |

## Composite Score

```python
composite = (
    0.40 * trending_score +   # Weight: 40%
    0.35 * success_score +    # Weight: 35%
    0.25 * trust_score        # Weight: 25%
)
```

**Ranking**:
| Score Range | Rank |
|------------|------|
| ≥ 80 | S (Top tier) |
| ≥ 65 | A (Excellent) |
| ≥ 50 | B (Good) |
| ≥ 35 | C (Average) |
| < 35 | D (Below average) |

## File Structure

```
streaming/spark_jobs/
├── unified_hot_path.py      # Full implementation with all UDFs
├── multi_topic_hot_path.py  # Multi-topic processing version
├── hot_path_scoring.py      # Original Trust-only via API
└── features_stream.py       # Feature engineering stream

models/
├── trending/
│   ├── trending_score.py    # V1 - Simple velocity
│   └── trending_score_v2.py # V2 - Time decay + engagement weight
│
└── success/
    ├── train_success_score.py    # V1 - 3-class LightGBM
    └── train_success_score_v2.py # V2 - Binary with price features
```

## Running the Pipeline

### Option 1: PowerShell Script
```powershell
.\scripts\start_unified_hot_path.ps1
```

### Option 2: Direct Docker Command
```bash
docker exec -it kol-spark-master spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
    /opt/spark-jobs/unified_hot_path.py
```

### Option 3: Local Testing
```bash
python streaming/spark_jobs/unified_hot_path.py --mode local
```

## Redis Output Schema

### Hash Key: `kol:scores:{platform}:{kol_id}`
```
{
    "kol_id": "username123",
    "platform": "tiktok",
    "trending_score": "75.5",
    "trending_label": "Hot",
    "success_score": "68.2",
    "success_label": "Medium",
    "trust_score": "82.0",
    "trust_label": "Highly Trustworthy",
    "composite_score": "74.3",
    "composite_rank": "A",
    "updated_at": "2024-12-05T10:30:00"
}
```

### Sorted Sets (for Ranking)
- `rank:composite:{platform}` → Top KOLs by composite score
- `rank:trending:{platform}` → Top KOLs by trending score

## Dependencies

```
pyspark >= 3.5.0
redis >= 4.0.0
joblib >= 1.0.0
numpy >= 1.20.0
lightgbm >= 3.0.0  # Optional, for Success model
```

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_TTL_SECONDS` | `3600` | Cache TTL (1 hour) |
| `MODEL_DIR` | `/opt/spark-jobs/models` | Model artifacts path |
| `CHECKPOINT_DIR` | `/tmp/spark_checkpoints` | Spark checkpoint |
| `TRIGGER_INTERVAL` | `10 seconds` | Streaming trigger |

## Architecture Comparison

| Aspect | Old (hot_path_scoring.py) | New (unified_hot_path.py) |
|--------|---------------------------|---------------------------|
| Scores | Trust only (via API) | Trust + Trending + Success |
| Trending | ❌ Not included | ✅ Velocity-based in Spark |
| Success | ❌ Not included | ✅ LightGBM + rule fallback |
| API calls | Required for ML | Optional (embedded UDFs) |
| Latency | Higher (HTTP calls) | Lower (in-process) |
| Scalability | Limited by API | Scales with Spark |

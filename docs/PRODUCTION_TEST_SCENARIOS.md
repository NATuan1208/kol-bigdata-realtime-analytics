# 🧪 Production Test Scenarios for KOL Analytics Platform

> **Version:** 1.0  
> **Author:** Principal Data Solutions Architect  
> **Date:** 2024-12-14  
> **Purpose:** Comprehensive production readiness testing guide

---

## 📋 Document Overview

This document provides detailed test scenarios to validate the KOL Analytics Platform is production-ready. Each scenario includes prerequisites, test steps, expected results, and validation criteria.

---

## 🎯 Test Categories

| Category | Focus Area | Priority |
|----------|------------|----------|
| **PROD-001** | Data Ingestion Pipeline | P0 (Critical) |
| **PROD-002** | Real-time Scoring (Hot Path) | P0 (Critical) |
| **PROD-003** | Batch Processing (Cold Path) | P1 (High) |
| **PROD-004** | API Performance & Reliability | P0 (Critical) |
| **PROD-005** | Dashboard Functionality | P1 (High) |
| **PROD-006** | Disaster Recovery | P1 (High) |
| **PROD-007** | Scale Testing | P2 (Medium) |
| **PROD-008** | Security Validation | P0 (Critical) |

---

## 🔥 PROD-001: Data Ingestion Pipeline

### Scenario 1.1: Kafka Topic Ingestion

**Objective:** Validate data flows correctly from Kafka to Bronze layer

**Prerequisites:**
- Redpanda/Kafka cluster running
- MinIO S3 available
- Producer script ready

**Test Steps:**
```bash
# 1. Produce test messages to Kafka
python scripts/import_json_to_kafka.py --topic kol-profiles-raw --file data/test_profiles.json

# 2. Verify messages in Kafka
docker exec redpanda rpk topic consume kol-profiles-raw --offset start --num 5

# 3. Run Bronze ingestion
python batch/etl/kafka_to_bronze_tiktok.py

# 4. Verify data in MinIO Bronze layer
docker exec minio mc ls local/lakehouse/bronze/tiktok/profiles/
```

**Expected Results:**
| Checkpoint | Expected | Status |
|------------|----------|--------|
| Messages in Kafka | ≥ 1 per profile | ⬜ |
| Bronze files created | JSON files in MinIO | ⬜ |
| No data loss | Input count = Bronze count | ⬜ |
| Processing time | < 60 seconds for 1000 records | ⬜ |

**Validation Query:**
```sql
-- Trino: Count Bronze records
SELECT COUNT(*) FROM bronze_tiktok_profiles;
```

---

### Scenario 1.2: Multi-source Ingestion

**Objective:** Test ingestion from multiple data sources simultaneously

**Test Steps:**
```bash
# Run parallel ingestion
parallel ::: \
  "python batch/etl/kafka_to_bronze_tiktok.py --topic kol-profiles-raw" \
  "python batch/etl/kafka_to_bronze_tiktok.py --topic kol-videos-raw" \
  "python batch/etl/kafka_to_bronze_tiktok.py --topic kol-comments-raw"
```

**Expected Results:**
- All three topics processed without conflicts
- No deadlocks or race conditions
- Data integrity maintained

---

## ⚡ PROD-002: Real-time Scoring (Hot Path)

### Scenario 2.1: Trending Score Calculation

**Objective:** Validate real-time trending scores are computed correctly

**Prerequisites:**
- Profiles loaded to Redis: `python scripts/load_profiles_to_redis.py`
- API server running

**Test Steps:**
```bash
# 1. Get trending KOLs
curl -X GET "http://localhost:8000/api/v1/trending?platform=tiktok&limit=15"

# 2. Verify score variance
python scripts/test_scoring_pipeline.py
```

**Expected Results:**
| Metric | Expected | Tolerance |
|--------|----------|-----------|
| Trending score range | 0-100 | N/A |
| Unique scores | ≥ 80% of KOLs | ±5% |
| Score variance | > 10 points spread | N/A |
| Response time | < 100ms | ±50ms |

**Validation Script:**
```python
import requests
import json

resp = requests.get("http://localhost:8000/api/v1/trending?platform=tiktok&limit=50")
data = resp.json()['data']

scores = [item['score'] for item in data]
unique_ratio = len(set(scores)) / len(scores)
score_range = max(scores) - min(scores)

print(f"Unique score ratio: {unique_ratio:.2%}")
print(f"Score range: {score_range:.1f}")

assert unique_ratio >= 0.8, "Too many duplicate scores!"
assert score_range >= 10, "Score variance too low!"
print("✅ Trending scoring test PASSED")
```

---

### Scenario 2.2: Trust Score API

**Objective:** Validate Trust Score ML model inference

**Test Steps:**
```bash
# 1. Call Trust API with known profile
curl -X POST "http://localhost:8000/predict/trust" \
  -H "Content-Type: application/json" \
  -d '{
    "kol_id": "test_kol_001",
    "followers_count": 1000000,
    "following_count": 500,
    "post_count": 200,
    "favorites_count": 50000000,
    "account_age_days": 1825,
    "verified": true,
    "has_bio": true,
    "has_url": true,
    "has_profile_image": true,
    "bio_length": 100
  }'

# 2. Call with different profile (should get different score)
curl -X POST "http://localhost:8000/predict/trust" \
  -H "Content-Type: application/json" \
  -d '{
    "kol_id": "test_kol_002",
    "followers_count": 1000,
    "following_count": 2000,
    "post_count": 5,
    "favorites_count": 100,
    "account_age_days": 30,
    "verified": false,
    "has_bio": false,
    "has_url": false,
    "has_profile_image": true,
    "bio_length": 0
  }'
```

**Expected Results:**
| Profile Type | Expected Trust Score | Reasoning |
|--------------|---------------------|-----------|
| High-quality KOL | 85-100 | Verified, old account, good ratio |
| Low-quality account | 20-50 | New, no bio, follow > follower |

---

### Scenario 2.3: End-to-End Scoring Pipeline

**Objective:** Validate complete scoring formula

**Formula Verification:**
```
Final Score = 0.40 × Trending + 0.35 × Success + 0.25 × Trust
```

**Test Steps:**
```python
# test_final_score.py
import requests

def get_kol_scores(kol_id):
    # Get trending
    trending = requests.get(f"http://localhost:8000/api/v1/trending?platform=tiktok&limit=100")
    trending_score = next((k['score'] for k in trending.json()['data'] if k['kol_id'] == kol_id), 0)
    
    # Get trust
    trust = requests.post("http://localhost:8000/predict/trust", json={...})
    trust_score = trust.json()['trust_score']
    
    # Calculate success (from engagement)
    # ... logic ...
    
    # Verify final formula
    expected_final = 0.4 * trending_score + 0.35 * success_score + 0.25 * trust_score
    
    return expected_final

# Test multiple KOLs
for kol in ["khaby.lame", "charlidamelio", "addisonre"]:
    score = get_kol_scores(kol)
    print(f"{kol}: {score:.1f}")
```

---

## 📊 PROD-003: Batch Processing (Cold Path)

### Scenario 3.1: ETL Pipeline Validation

**Objective:** Test Bronze → Silver → Gold transformation

**Test Steps:**
```bash
# 1. Run Bronze to Silver
spark-submit batch/etl/bronze_to_silver.py

# 2. Verify Silver layer
docker exec trino trino --execute "SELECT COUNT(*) FROM iceberg.silver.kol_profiles_tiktok"

# 3. Run Silver to Gold
spark-submit batch/etl/silver_to_gold.py

# 4. Verify Gold layer
docker exec trino trino --execute "SELECT * FROM iceberg.gold.kol_summary LIMIT 5"
```

**Expected Results:**
| Layer | Validation | Expected |
|-------|------------|----------|
| Bronze | Raw records preserved | 100% of source |
| Silver | Cleaned, normalized | ≥ 95% of Bronze |
| Gold | Aggregated metrics | Summary per KOL |

---

### Scenario 3.2: Data Quality Checks

**Objective:** Validate data quality in each layer

**Quality Rules:**
```python
# data_quality_checks.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, isnan, isnull

spark = SparkSession.builder.getOrCreate()

# Load Silver data
silver_df = spark.read.parquet("s3a://lakehouse/silver/kol_profiles_tiktok/")

# Quality checks
checks = {
    "no_null_usernames": silver_df.filter(col("username").isNull()).count() == 0,
    "positive_followers": silver_df.filter(col("followers_count") < 0).count() == 0,
    "valid_platform": silver_df.filter(~col("platform").isin(["tiktok", "youtube"])).count() == 0,
    "reasonable_engagement": silver_df.filter(col("favorites_count") > col("followers_count") * 1000).count() < silver_df.count() * 0.01,
}

for check_name, passed in checks.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {check_name}")
```

---

## 🌐 PROD-004: API Performance & Reliability

### Scenario 4.1: Load Testing

**Objective:** Validate API can handle production load

**Test Steps:**
```bash
# Install load testing tool
pip install locust

# Run load test
locust -f tests/load_test.py --headless -u 100 -r 10 -t 60s
```

**Load Test File:**
```python
# tests/load_test.py
from locust import HttpUser, task, between

class KOLAPIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_trending(self):
        self.client.get("/api/v1/trending?platform=tiktok&limit=20")
    
    @task(2)
    def get_health(self):
        self.client.get("/health")
    
    @task(1)
    def predict_trust(self):
        self.client.post("/predict/trust", json={
            "kol_id": "test",
            "followers_count": 100000,
            "following_count": 500,
            "post_count": 50,
            "favorites_count": 1000000,
            "account_age_days": 365,
            "verified": True,
            "has_bio": True,
            "has_url": False,
            "has_profile_image": True,
            "bio_length": 50
        })
```

**Expected Results:**
| Metric | Target | Minimum |
|--------|--------|---------|
| Avg Response Time | < 100ms | < 500ms |
| 95th Percentile | < 200ms | < 1000ms |
| Error Rate | 0% | < 1% |
| Throughput | 500 req/s | 100 req/s |

---

### Scenario 4.2: API Endpoint Validation

**Objective:** Test all API endpoints

```bash
# Run API endpoint tests
python tests/test_api_endpoints.py

# Expected output:
# ✅ GET /health - 200 OK (23ms)
# ✅ GET /api/v1/trending - 200 OK (45ms)
# ✅ POST /predict/trust - 200 OK (89ms)
# ✅ POST /predict/success - 200 OK (76ms)
# ✅ GET /api/v1/kols - 200 OK (156ms)
```

---

## 📺 PROD-005: Dashboard Functionality

### Scenario 5.1: Tab 1 - Real-time Trending

**Objective:** Validate real-time dashboard displays correct data

**Manual Test Steps:**
1. Open dashboard: `http://localhost:8501`
2. Select Platform = "tiktok"
3. Click "🔄 Refresh Trending"
4. Verify:
   - [ ] Top 15 KOLs displayed
   - [ ] Trending scores vary (not all same)
   - [ ] Trust scores calculated per KOL
   - [ ] Final composite score shown
   - [ ] Metrics cards show correct values

**Screenshot Checklist:**
```
Tab 1 Requirements:
├── Header shows "KOL Trending Analysis"
├── Metrics row shows:
│   ├── Top Trending Score (highest score)
│   ├── Average Trust (mean of trust scores)
│   ├── Platform (selected platform)
│   └── Last Update (timestamp)
├── Table shows:
│   ├── kol_id (unique per row)
│   ├── trending_score (0-100, varies)
│   ├── trust_score (calculated per profile)
│   ├── success_score (engagement-based)
│   └── final_score (weighted composite)
└── Chart shows score breakdown
```

---

### Scenario 5.2: Tab 2 - Cold Path Analytics

**Objective:** Validate batch data display

**Manual Test Steps:**
1. Navigate to Tab 2 "KOL Scorecard"
2. Apply filters:
   - Platform: tiktok
   - Tier: All
   - Sort by: followers_count
3. Verify:
   - [ ] Shows actual follower counts (not hardcoded 50,000)
   - [ ] Favorites count (likes) displayed
   - [ ] Engagement ratio calculated correctly
   - [ ] Tier distribution chart accurate
   - [ ] Score breakdown chart shows variance

**Validation:**
```python
# Check actual data is displayed, not placeholders
import requests
import json

# Load from dashboard's data source
import redis
r = redis.Redis(host='localhost', port=16379, decode_responses=True)
profiles = json.loads(r.get("kol:profiles:list:tiktok"))

# Verify unique follower counts
followers = [p['followers_count'] for p in profiles]
unique_followers = len(set(followers))

assert unique_followers >= len(followers) * 0.8, "Too many duplicate follower counts!"
print(f"✅ {unique_followers} unique follower counts out of {len(followers)} profiles")
```

---

## 💾 PROD-006: Disaster Recovery

### Scenario 6.1: Redis Failover

**Objective:** Test system behavior when Redis is unavailable

**Test Steps:**
```bash
# 1. Stop Redis
docker stop kol-redis

# 2. Test API behavior
curl -X GET "http://localhost:8000/api/v1/trending?platform=tiktok"
# Expected: Graceful error response or fallback data

# 3. Restart Redis
docker start kol-redis

# 4. Reload data
python scripts/load_profiles_to_redis.py

# 5. Verify recovery
curl -X GET "http://localhost:8000/api/v1/trending?platform=tiktok"
```

**Expected Results:**
- API returns error gracefully (no 500 crash)
- Dashboard shows appropriate error message
- System recovers automatically when Redis returns

---

### Scenario 6.2: Data Backup & Restore

**Objective:** Validate backup/restore procedures

**Test Steps:**
```bash
# 1. Create Redis backup
docker exec kol-redis redis-cli BGSAVE
docker cp kol-redis:/data/dump.rdb ./backup/redis_dump.rdb

# 2. Export profiles to JSON
python -c "
import redis, json
r = redis.Redis(host='localhost', port=16379, decode_responses=True)
data = r.get('kol:profiles:list:tiktok')
with open('backup/profiles_backup.json', 'w') as f:
    f.write(data)
print('Backup created')
"

# 3. Simulate data loss
docker exec kol-redis redis-cli FLUSHALL

# 4. Restore from backup
python scripts/load_profiles_to_redis.py
# OR
# docker cp ./backup/redis_dump.rdb kol-redis:/data/dump.rdb
# docker restart kol-redis

# 5. Verify restoration
python scripts/test_scoring_pipeline.py
```

---

## 📈 PROD-007: Scale Testing

### Scenario 7.1: Large Dataset Processing

**Objective:** Test with 100K+ KOL profiles

**Test Steps:**
```bash
# 1. Generate large dataset
python -c "
import json
import random

profiles = []
for i in range(100000):
    profiles.append({
        'username': f'kol_{i:06d}',
        'followers_count': random.randint(1000, 10000000),
        'favorites_count': random.randint(100, 100000000),
        'post_count': random.randint(1, 5000),
        'platform': 'tiktok'
    })

with open('data/large_dataset.json', 'w') as f:
    json.dump(profiles, f)
"

# 2. Time the ingestion
time python scripts/load_profiles_to_redis.py --file data/large_dataset.json

# 3. Test query performance
time curl "http://localhost:8000/api/v1/trending?limit=100"
```

**Performance Targets:**
| Operation | 10K profiles | 100K profiles |
|-----------|--------------|---------------|
| Redis Load | < 30s | < 5min |
| API Query | < 100ms | < 500ms |
| Dashboard Load | < 2s | < 10s |

---

## 🔐 PROD-008: Security Validation

### Scenario 8.1: Input Validation

**Objective:** Test API input sanitization

**Test Steps:**
```bash
# SQL Injection attempt
curl -X GET "http://localhost:8000/api/v1/trending?platform=tiktok'; DROP TABLE users;--"
# Expected: 400 Bad Request or sanitized input

# XSS attempt
curl -X POST "http://localhost:8000/predict/trust" \
  -d '{"kol_id": "<script>alert(1)</script>", "followers_count": 1000}'
# Expected: Input escaped/sanitized

# Large payload
dd if=/dev/zero bs=10M count=1 | curl -X POST "http://localhost:8000/predict/trust" -d @-
# Expected: 413 Payload Too Large
```

---

### Scenario 8.2: Rate Limiting

**Objective:** Verify rate limiting is functional

```bash
# Send 100 requests in quick succession
for i in {1..100}; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/v1/trending"
done | sort | uniq -c

# Expected: Most return 200, some return 429 (rate limited)
```

---

## ✅ Production Readiness Checklist

### Pre-deployment

- [ ] All PROD-001 to PROD-008 scenarios passed
- [ ] Load testing completed with acceptable results
- [ ] Security scan completed
- [ ] Backup/restore procedure tested
- [ ] Monitoring alerts configured
- [ ] Runbook documentation complete

### Deployment Day

- [ ] Database migrations applied
- [ ] Feature flags configured
- [ ] Health checks passing
- [ ] Smoke tests successful
- [ ] Rollback plan ready

### Post-deployment

- [ ] Monitor error rates for 24 hours
- [ ] Verify data consistency
- [ ] Check performance metrics
- [ ] Confirm all integrations working
- [ ] Update documentation

---

## 📝 Test Execution Log Template

```markdown
## Test Execution: [DATE]

**Tester:** [Name]
**Environment:** [Dev/Staging/Prod]

### Results Summary

| Scenario | Status | Notes |
|----------|--------|-------|
| PROD-001.1 | ✅ | All passed |
| PROD-001.2 | ✅ | Minor warning |
| PROD-002.1 | ✅ | 15 unique scores |
| ... | ... | ... |

### Issues Found

1. **Issue:** [Description]
   - **Severity:** [P0/P1/P2]
   - **Steps to reproduce:** ...
   - **Expected vs Actual:** ...
   - **Screenshot:** [link]

### Sign-off

- [ ] QA Lead approved
- [ ] Dev Lead approved
- [ ] Ops Lead approved
```

---

*This document should be reviewed and updated before each production release.*

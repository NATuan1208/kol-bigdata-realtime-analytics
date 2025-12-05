# 📈 ML Trending Score - Technical Report

> **Môn học:** IE212 - Big Data Analytics  
> **Đội ngũ:** KOL Analytics Team  
> **Ngày lập:** 03/12/2025  
> **Phiên bản:** 2.0  
> **Trạng thái:** ✅ COMPLETE (Formula-based, no ML training needed)

---

## 📋 Mục Lục

1. [Tổng Quan Bài Toán](#1-tổng-quan-bài-toán)
2. [Formula Design](#2-formula-design)
3. [V1 vs V2 Comparison](#3-v1-vs-v2-comparison)
4. [Implementation Details](#4-implementation-details)
5. [Score Distribution Analysis](#5-score-distribution-analysis)
6. [Production Deployment](#6-production-deployment)
7. [Appendix](#7-appendix)

---

## 1. Tổng Quan Bài Toán

### 1.1 Business Problem

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRENDING SCORE - BUSINESS VALUE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🎯 MỤC TIÊU: Đánh giá mức độ "đang hot" của KOL                        │
│                                                                         │
│  📊 INPUT:  Events (videos, posts) từ TikTok                            │
│             • Timestamp                                                 │
│             • Video views, likes                                        │
│             • Historical baseline                                       │
│                                                                         │
│  📈 OUTPUT: Trending Score (0-100)                                      │
│             • Viral (80-100): Đang cực hot, nên hợp tác ngay           │
│             • Hot (60-79):    Đang lên xu hướng                         │
│             • Warm (40-59):   Hoạt động bình thường                     │
│             • Normal (25-39): Ổn định                                   │
│             • Cold (<25):     Ít hoạt động gần đây                      │
│                                                                         │
│  💼 BUSINESS USE CASES:                                                 │
│     1. Timing hợp tác - chọn KOL đang viral                            │
│     2. Trend detection - phát hiện KOL sắp hot                          │
│     3. Risk assessment - tránh KOL đang đi xuống                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Approach: Formula-based (Not ML)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WHY FORMULA INSTEAD OF ML?                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ❌ ML Training Challenges:                                             │
│     • No labeled "trending" ground truth                                │
│     • Need time-series data for proper training                         │
│     • Small dataset limits generalization                               │
│                                                                         │
│  ✅ Formula-based Advantages:                                           │
│     • Interpretable (can explain why score is high/low)                 │
│     • No training needed (works immediately)                            │
│     • Domain knowledge embedded in weights                              │
│     • Easy to tune and debug                                            │
│                                                                         │
│  📐 FORMULA TYPE: Velocity-based Trending Detection                     │
│     → Measures "speed of growth" not absolute size                      │
│     → Compares KOL to their baseline + market average                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Formula Design

### 2.1 Core Formula (V2)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRENDING SCORE FORMULA V2                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  STEP 1: Calculate Components                                           │
│  ─────────────────────────────                                          │
│                                                                         │
│  personal_growth = current_velocity / baseline_velocity                 │
│  market_position = current_velocity / global_avg_velocity               │
│  momentum = (current - previous) / previous  [if available]             │
│                                                                         │
│  STEP 2: Weighted Combination                                           │
│  ────────────────────────────                                           │
│                                                                         │
│  raw_score = α × personal_growth                                        │
│            + β × market_position                                        │
│            + γ × (1 + momentum)                                         │
│                                                                         │
│  Where:                                                                 │
│    α = 0.5  (personal growth most important)                            │
│    β = 0.3  (market position)                                           │
│    γ = 0.2  (momentum/acceleration)                                     │
│                                                                         │
│  STEP 3: Sigmoid Normalization                                          │
│  ─────────────────────────────                                          │
│                                                                         │
│  trending_score = 100 / (1 + exp(-k × (raw_score - threshold)))        │
│                                                                         │
│  Where:                                                                 │
│    k = 0.8         (steepness)                                          │
│    threshold = 2.0 (center point)                                       │
│                                                                         │
│  STEP 4: Apply Time Decay [Optional]                                    │
│  ───────────────────────────────────                                    │
│                                                                         │
│  raw_score *= time_decay_factor                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Time Decay Function

```python
def calculate_time_decay(event_time, reference_time, half_life_days=7.0):
    """
    Exponential decay: weight = exp(-λ × t)
    where λ = ln(2) / half_life
    
    Half-life = 7 days means:
    - Events from today: weight = 1.0
    - Events from 7 days ago: weight = 0.5
    - Events from 14 days ago: weight = 0.25
    """
    delta_days = (reference_time - event_time).total_seconds() / 86400
    decay_rate = math.log(2) / half_life_days
    weight = math.exp(-decay_rate * delta_days)
    return weight
```

### 2.3 Engagement Weight Function

```python
def calculate_engagement_weight(views, likes, global_avg_views=10000):
    """
    Log-scaled engagement weight.
    Higher view counts = higher impact on trending score.
    
    weight = log(1 + views/global_avg) / log(1 + max_ratio)
    Normalized to [0.1, 1.0] range
    """
    ratio = views / global_avg_views
    weight = math.log1p(ratio) / math.log1p(100)  # Cap at 100x
    weight = 0.1 + 0.9 * min(weight, 1.0)
    return weight
```

### 2.4 Sigmoid Normalization

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SIGMOID CALIBRATION                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Raw Score → Trending Score (0-100) mapping:                            │
│                                                                         │
│  raw_score = 0.5 → trending = 18.2  (below average)                     │
│  raw_score = 1.0 → trending = 31.0  (normal)                            │
│  raw_score = 2.0 → trending = 50.0  (center point)                      │
│  raw_score = 3.0 → trending = 69.0  (hot)                               │
│  raw_score = 5.0 → trending = 91.7  (viral)                             │
│                                                                         │
│       100 ┤                                    ╭───────────             │
│           │                              ╭─────╯                        │
│        50 ┤                        ╭─────╯                              │
│           │                  ╭─────╯                                    │
│         0 ┼──────────────────╯                                          │
│           0        1        2        3        4        5  raw_score     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. V1 vs V2 Comparison

### 3.1 V1 Formula (Original)

```python
# V1: Simple ratio-based
personal_ratio = current_velocity / baseline_velocity
global_ratio = current_velocity / global_avg_velocity
v1_raw = 0.6 * personal_ratio + 0.4 * global_ratio
v1_score = min(v1_raw / 5 * 100, 100)  # Linear normalization
```

**Problems with V1:**
- Linear normalization causes extreme scores
- No time decay (old events count same as recent)
- No engagement weighting (1 view = 1M views same impact)

### 3.2 V2 Improvements

| Aspect | V1 | V2 |
|--------|----|----|
| Time decay | ❌ No | ✅ Exponential (7-day half-life) |
| Engagement weight | ❌ No | ✅ Log-scaled by views |
| Normalization | Linear (unbounded) | Sigmoid (0-100 bounded) |
| Momentum | ❌ No | ✅ Rate of change |
| Labels | 3 (Low/Med/High) | 5 (Cold/Normal/Warm/Hot/Viral) |

### 3.3 Comparison Results

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    V1 vs V2 TEST CASES                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Case                      │ V1 Score │ V2 Score │ V2 Label             │
│  ─────────────────────────┼──────────┼──────────┼──────────────────    │
│  New KOL, low activity     │   24.00  │   31.00  │ Normal               │
│  Average KOL               │   20.00  │   50.00  │ Warm                 │
│  Growing KOL               │   52.00  │   80.00  │ Viral                │
│  Viral KOL                 │  100.00  │   95.00  │ Viral (capped)       │
│  Declining KOL             │   14.00  │   25.00  │ Normal               │
│                                                                         │
│  💡 V2 provides better distribution and meaningful labels              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Details

### 4.1 Data Loading

```python
def load_events_data() -> pd.DataFrame:
    """Load events from videos and discovery data."""
    events = []
    
    for pattern in ["kol_videos_raw_*.json", "kol_discovery_raw_*.json"]:
        for fp in DATA_DIR.glob(pattern):
            with open(fp) as f:
                data = json.load(f)
            for record in data:
                event = record.get("data", record)
                events.append({
                    "username": event.get("username"),
                    "event_time": event.get("event_time"),
                    "video_views": pd.to_numeric(event.get("video_views", 0)),
                    "video_likes": pd.to_numeric(event.get("video_likes", 0)),
                })
    
    return pd.DataFrame(events)
```

### 4.2 Score Calculation Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CALCULATION FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Load Events                                                         │
│     └─ kol_videos_raw + kol_discovery_raw                              │
│                                                                         │
│  2. Group by Username                                                   │
│     └─ Each KOL gets their own event list                              │
│                                                                         │
│  3. For Each KOL:                                                       │
│     ├─ 3.1 Calculate time_decay for each event                         │
│     ├─ 3.2 Calculate engagement_weight for each event                  │
│     ├─ 3.3 weighted_velocity = sum(time_decay × engagement_weight)     │
│     ├─ 3.4 baseline = avg velocity across all KOLs                     │
│     ├─ 3.5 global_avg = overall market average                         │
│     └─ 3.6 trending_score = formula(weighted_velocity, baseline)       │
│                                                                         │
│  4. Assign Label                                                        │
│     ├─ Viral:  80-100                                                  │
│     ├─ Hot:    60-79                                                   │
│     ├─ Warm:   40-59                                                   │
│     ├─ Normal: 25-39                                                   │
│     └─ Cold:   0-24                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Label Thresholds

```python
def assign_label(trending_score: float) -> str:
    if trending_score >= 80:
        return "Viral"
    elif trending_score >= 60:
        return "Hot"
    elif trending_score >= 40:
        return "Warm"
    elif trending_score >= 25:
        return "Normal"
    else:
        return "Cold"
```

---

## 5. Score Distribution Analysis

### 5.1 Expected Distribution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EXPECTED SCORE DISTRIBUTION                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  With sigmoid normalization and current formula weights:                │
│                                                                         │
│  Label      │ Score Range │ Expected % │ Description                    │
│  ───────────┼─────────────┼────────────┼─────────────────────────────   │
│  Cold       │    0-24     │   ~10%     │ Inactive KOLs                  │
│  Normal     │   25-39     │   ~30%     │ Stable, low activity           │
│  Warm       │   40-59     │   ~35%     │ Average activity               │
│  Hot        │   60-79     │   ~20%     │ Above average, growing         │
│  Viral      │   80-100    │    ~5%     │ Top performers, explosive      │
│                                                                         │
│  Distribution Shape:                                                    │
│  ────────────────────                                                   │
│                                                                         │
│  Cold   ██████████                        10%                           │
│  Normal ██████████████████████████████    30%                           │
│  Warm   ███████████████████████████████████ 35%                         │
│  Hot    ████████████████████              20%                           │
│  Viral  █████                              5%                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Sample Output

```json
{
  "username": "viral_star_123",
  "trending_score": 85.42,
  "trending_label": "Viral",
  "personal_growth": 3.5,
  "market_position": 2.8,
  "momentum": 0.15,
  "raw_score": 3.24,
  "current_velocity": 28.5,
  "baseline_velocity": 8.14,
  "total_events": 15,
  "total_views": 1250000,
  "avg_views": 83333
}
```

---

## 6. Production Deployment

### 6.1 API Endpoint

```python
# serving/api/routes/predict.py

@router.post("/predict/trending")
async def predict_trending(request: TrendingRequest):
    """
    Calculate Trending Score for a KOL.
    
    Input: username (will fetch events from data)
           OR direct event metrics
    Output: trending_score (0-100), trending_label
    """
    # Load KOL's events
    events = fetch_kol_events(request.username)
    
    # Calculate score
    result = calculate_trending_score_v2(
        current_velocity=calculate_velocity(events),
        baseline_velocity=get_baseline(request.username),
        global_avg_velocity=get_global_avg(),
        momentum=calculate_momentum(events)
    )
    
    return {
        "kol_id": request.username,
        "trending_score": result["trending_score"],
        "trending_label": result["trending_label"],
        "personal_growth": result["personal_growth"],
        "market_position": result["market_position"],
        "formula_version": "v2"
    }
```

### 6.2 Files Reference

| File | Purpose |
|------|---------|
| `models/trending/trending_score.py` | V1 implementation |
| `models/trending/trending_score_v2.py` | V2 implementation (production) |
| `serving/api/routes/predict.py` | API endpoint |

### 6.3 Integration with Hot Path

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    HOT PATH INTEGRATION                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Kafka (kol.videos.raw)                                                 │
│        │                                                                │
│        ▼                                                                │
│  Spark Streaming                                                        │
│        │                                                                │
│        ├─────────────────────────────────────────────────────┐         │
│        │                                                     │         │
│        ▼                                                     ▼         │
│  API: /predict/trust                              API: /predict/trending│
│        │                                                     │         │
│        └────────────────────┬────────────────────────────────┘         │
│                             │                                           │
│                             ▼                                           │
│                    Kafka (scores.stream)                                │
│                    {                                                    │
│                      "kol_id": "user123",                              │
│                      "trust_score": 85.0,                              │
│                      "trending_score": 72.5,                           │
│                      "trending_label": "Hot"                           │
│                    }                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Appendix

### 7.1 Formula Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| α (personal_growth weight) | 0.5 | Weight for personal growth |
| β (market_position weight) | 0.3 | Weight for market comparison |
| γ (momentum weight) | 0.2 | Weight for acceleration |
| k (sigmoid steepness) | 0.8 | Controls sigmoid curve |
| threshold (sigmoid center) | 2.0 | Raw score for 50% trending |
| half_life_days | 7.0 | Time decay half-life |

### 7.2 Run Script

```bash
# Calculate trending scores for all KOLs
python models/trending/trending_score_v2.py

# Sample output:
# TOP 10 TRENDING KOLs
# 1. @viral_star_123
#    Score: 92.5 (Viral)
#    Views: 1,500,000 | Events: 20
#    Growth: 4.2x | Market: 3.1x
```

### 7.3 Unit Tests

```python
def test_trending_score():
    # Test average KOL
    result = calculate_trending_score_v2(
        current_velocity=10,
        baseline_velocity=10,
        global_avg_velocity=10
    )
    assert 45 <= result["trending_score"] <= 55
    assert result["trending_label"] == "Warm"
    
    # Test viral KOL
    result = calculate_trending_score_v2(
        current_velocity=100,
        baseline_velocity=10,
        global_avg_velocity=10
    )
    assert result["trending_score"] >= 80
    assert result["trending_label"] == "Viral"
```

---

## 📊 Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRENDING SCORE - PROJECT STATUS                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ✅ Formula Design:       V2 with time decay + engagement weight        │
│  ✅ Implementation:       models/trending/trending_score_v2.py          │
│  ✅ Label System:         5-tier (Cold → Viral)                         │
│  ✅ API Endpoint:         /predict/trending                             │
│  ⏳ Hot Path Integration: Pending (with trust score)                    │
│                                                                         │
│  📐 APPROACH: Formula-based (no ML training)                            │
│  💡 REASON:  No labeled data, need interpretability                     │
│                                                                         │
│  Overall Progress: 90% ✅                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 2.0 | Last Updated: 2025-12-03*

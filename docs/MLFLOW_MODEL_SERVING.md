# MLflow Model Registry & Serving Guide

## 📋 Tổng quan

Document này giải thích quy trình đăng ký model lên MLflow Registry và cách sử dụng Prediction API cho bài toán **KOL Trust Score Assessment**.

---

## 0. Bài Toán Business

### 0.1 Mục tiêu

**Đánh giá độ tin cậy của KOL (Key Opinion Leader)** để giúp brands/agencies quyết định có nên hợp tác marketing hay không.

```
┌─────────────────────────────────────────────────────────────────┐
│           BÀI TOÁN: KOL TRUST SCORE ASSESSMENT                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  INPUT:  Các chỉ số profile & hoạt động của KOL                 │
│          - Followers, Following, Posts                          │
│          - Engagement (likes, comments)                         │
│          - Account age, Verification status                     │
│          - Profile completeness (bio, avatar, URL)              │
│                                                                 │
│  OUTPUT: Trust Score (0-100%)                                   │
│          - Điểm càng CAO = KOL càng ĐÁNG TIN                    │
│          - Điểm càng THẤP = KOL có dấu hiệu KHÔNG ĐÁNG TIN      │
│                                                                 │
│  BUSINESS VALUE:                                                │
│          - Brand biết KOL nào nên hợp tác                       │
│          - Tránh lãng phí budget cho fake influencers           │
│          - Giảm rủi ro campaign marketing                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 0.2 ĐÂY KHÔNG PHẢI Bot Detection!

| Aspect | Bot Detection | **KOL Trust Assessment** ✅ |
|--------|---------------|------------------------------|
| Câu hỏi | "Account này là bot?" | "KOL này có đáng tin để hợp tác?" |
| Đối tượng | Mọi account | KOLs/Influencers |
| Mục đích | Loại bỏ spam | **Đánh giá chất lượng hợp tác** |
| Output | is_bot (Yes/No) | **Trust Score (0-100%)** |
| Business | Platform moderation | **Marketing decision support** |

### 0.3 Tại sao dùng Bot Detection Dataset?

Dataset **Twitter Human-Bot** được **re-purpose** cho bài toán Trust Score vì:

```
Bot Patterns ≈ Untrustworthy KOL Patterns (~80% overlap)
───────────────────────────────────────────────────────
├── Fake/Bought followers      → Low organic engagement
├── F/F ratio bất thường       → Suspicious growth  
├── High posting frequency     → Spam-like behavior
├── Incomplete profile         → Low authenticity
└── Abnormal growth patterns   → Possibly purchased metrics
```

**Semantic Re-mapping:**
- `is_bot = 1` → KOL không đáng tin (có patterns giống bot/fake)
- `is_bot = 0` → KOL đáng tin (organic, authentic)

### 0.4 ⚠️ LƯU Ý QUAN TRỌNG KHI TRÌNH BÀY

```
┌─────────────────────────────────────────────────────────────────┐
│              KEY POINTS KHI TRÌNH BÀY / BÁO CÁO                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ❌ SAI: "Đây là bài toán Bot Detection"                        │
│  ✅ ĐÚNG: "Đây là bài toán đánh giá độ tin cậy KOL"             │
│                                                                 │
│  ❌ SAI: "Model detect account là bot hay không"                │
│  ✅ ĐÚNG: "Model đánh giá KOL có đáng tin để hợp tác không"     │
│                                                                 │
│  ❌ SAI: "Output là is_bot = True/False"                        │
│  ✅ ĐÚNG: "Output là Trust Score 0-100%"                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  📝 GIẢI THÍCH VỀ DATASET:                                      │
│                                                                 │
│  • Dataset bot detection được RE-PURPOSE cho bài toán Trust     │
│  • Vì: Bot patterns ≈ Untrustworthy KOL patterns (~80% overlap) │
│  • Dataset chỉ là PROXY cho untrustworthy behavioral patterns   │
│  • Model học nhận diện PATTERNS, không phải detect bot          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  💼 BUSINESS VALUE:                                             │
│                                                                 │
│  • Giúp brands đánh giá KOL trước khi hợp tác                   │
│  • Tiết kiệm marketing budget (tránh fake influencers)          │
│  • Giảm rủi ro campaign marketing                               │
│  • Automated screening thay vì manual verification              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Model Registration - Đăng ký Model lên MLflow

### 1.1 Models đã đăng ký

| Model Name | Stage | ROC-AUC | Mô tả |
|------------|-------|---------|-------|
| `trust-score-lightgbm-optuna` | **Production** | 0.9423 | Best model - LightGBM với Optuna tuning |
| `trust-score-ensemble` | Staging | 0.9421 | Ensemble (XGBoost + LightGBM + IsolationForest) |

### 1.2 Quy trình đăng ký

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Train Model   │────▶│  Log to MLflow  │────▶│ Register Model  │
│   (Optuna)      │     │  (Experiment)   │     │   (Registry)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                              ┌──────────┐       ┌──────────┐       ┌──────────┐
                              │   None   │──────▶│ Staging  │──────▶│Production│
                              └──────────┘       └──────────┘       └──────────┘
```

**Script đăng ký:** `models/registry/register_trust_models.py`

```bash
# Chạy trong trainer container
docker exec kol-trainer python -m models.registry.register_trust_models
```

---

## 2. Model Lifecycle - Vòng đời Model

### 2.1 Các Stage trong MLflow

| Stage | Ý nghĩa | Sử dụng |
|-------|---------|---------|
| **None** | Mới đăng ký, chưa validate | Development/Testing |
| **Staging** | Đã test, đang chờ approve | A/B Testing, Shadow mode |
| **Production** | Đã approve, serving chính thức | Real-time prediction |
| **Archived** | Model cũ, không dùng nữa | Lưu trữ lịch sử |

### 2.2 Quy trình chuyển Stage

```
1. Train new model với Optuna
2. Đăng ký lên Registry (Stage = None)
3. Chạy validation tests
4. Promote to Staging (A/B test với model cũ)
5. Nếu metrics tốt hơn → Promote to Production
6. Model cũ → Archived
```

### 2.3 Tự động hóa (trong tương lai)

```python
# Ví dụ: Auto-promote nếu metrics tốt hơn
if new_model_auc > current_prod_auc + 0.01:  # Cải thiện > 1%
    promote_to_production(new_model)
    archive_old_model(current_prod)
```

---

## 3. Prediction API

### 3.1 Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/predict/trust` | POST | Predict cho 1 KOL |
| `/predict/trust/batch` | POST | Predict cho nhiều KOLs |
| `/predict/trust/features` | POST | Predict từ features đã engineer |
| `/predict/trust/model-info` | GET | Thông tin model đang dùng |

### 3.2 Input - Dữ liệu đầu vào

**Raw Features (đơn giản - API tự engineer):**

```json
{
    "kol_id": "user_123",
    "followers_count": 100000,      // Số followers
    "following_count": 500,         // Số following
    "post_count": 2000,             // Số bài đăng
    "favorites_count": 500000,      // Tổng likes nhận được
    "account_age_days": 2000,       // Tuổi tài khoản (ngày)
    "verified": true,               // Đã xác minh?
    "has_bio": true,                // Có bio?
    "has_url": true,                // Có URL trong profile?
    "has_profile_image": true,      // Có avatar?
    "bio_length": 150               // Độ dài bio
}
```

**Engineered Features (29 features - từ batch processing):**

Model thực sự sử dụng 29 features được engineer từ raw data:

| Feature | Công thức | Ý nghĩa |
|---------|-----------|---------|
| `log_followers` | log(followers + 1) | Giảm skew của followers |
| `followers_following_ratio` | followers / following | Tỷ lệ FF (bot thường ≈ 1) |
| `posts_per_day` | posts / age_days | Tần suất đăng bài |
| `engagement_rate` | favorites / posts | Mức độ tương tác |
| `profile_completeness` | (bio + url + image) / 3 | Độ hoàn thiện profile |
| `suspicious_growth` | 1 nếu growth > 100/day & age < 180 | Flag tăng trưởng bất thường |
| `fake_follower_indicator` | 1 nếu followers > 10k & engagement < 0.1 | Flag fake followers |
| ... | ... | ... |

### 3.3 Output - Kết quả trả về

```json
{
    "kol_id": "user_123",
    "trust_score": 92.84,           // Điểm tin cậy (0-100)
    "is_trustworthy": true,         // Phân loại nhị phân
    "confidence": 0.9284,           // Độ tin cậy của prediction
    "risk_level": "low",            // Mức độ rủi ro
    "prediction_source": "realtime", // Nguồn: realtime hoặc batch
    "model_version": "trust-score-lightgbm-optuna-Production",
    "timestamp": "2025-11-27T07:01:06"
}
```

### 3.4 Giải thích Output

| Field | Giá trị | Ý nghĩa |
|-------|---------|---------|
| `trust_score` | 0-100 | Điểm tin cậy, càng cao càng đáng tin |
| `is_trustworthy` | true/false | True nếu trust_score >= 50 |
| `confidence` | 0-1 | Model tự tin bao nhiêu với prediction |
| `risk_level` | low/moderate/elevated/high | Phân loại rủi ro |

**Risk Level Mapping:**

| Trust Score | Risk Level | Ý nghĩa |
|-------------|------------|---------|
| 80-100 | Low | KOL rất đáng tin, hợp tác an toàn |
| 60-79 | Moderate | Cần kiểm tra thêm trước khi hợp tác |
| 40-59 | Elevated | Nhiều dấu hiệu đáng ngờ |
| 0-39 | High | Rất có thể là bot/fake account |

---

## 4. Bug Fix: Logic Sai Ban Đầu

### 4.1 Vấn đề

Ban đầu API trả về kết quả ngược:
- Profile legit (verified, engagement cao) → Trust Score = **7.16%** ❌
- Profile suspicious (no bio, spam) → Trust Score = **90%+** ❌

### 4.2 Nguyên nhân

**Model được train với label:**
- `1` = Bot/Fake (untrustworthy)
- `0` = Human/Real (trustworthy)

**LightGBM Booster.predict() trả về:** P(class=1) = P(bot/fake)

**Code ban đầu (SAI):**
```python
trust_proba = model.predict(features)[0]  # Đây là P(bot)!
trust_score = trust_proba * 100           # Sai!
```

### 4.3 Fix

```python
# LightGBM Booster returns P(fake/bot)
fake_proba = model.predict(features)[0]
trust_proba = 1.0 - float(fake_proba)     # Trust = 1 - P(bot)
trust_score = trust_proba * 100
```

### 4.4 Kết quả sau fix

| Profile | Trust Score | Risk Level |
|---------|-------------|------------|
| Legit KOL (verified, good engagement) | **92.84%** ✅ | Low |
| Suspicious Bot (no bio, spam activity) | **24.47%** ✅ | High |

---

## 5. Test Cases

### 5.1 Test Legit KOL

```powershell
$body = @{
    kol_id = "legit_kol"
    followers_count = 100000
    following_count = 500
    post_count = 2000
    favorites_count = 500000
    account_age_days = 2000
    verified = $true
    has_bio = $true
    has_url = $true
    has_profile_image = $true
    bio_length = 150
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/predict/trust" -Method Post -Body $body -ContentType "application/json"
```

**Expected:** Trust Score > 80%, Risk Level = "low"

### 5.2 Test Suspicious Bot

```powershell
$body = @{
    kol_id = "suspicious_bot"
    followers_count = 50000
    following_count = 50000      # FF ratio ≈ 1 (suspicious)
    post_count = 10000           # Spam activity
    favorites_count = 100        # Low engagement
    account_age_days = 30        # New account
    verified = $false
    has_bio = $false             # No bio
    has_url = $false
    has_profile_image = $false   # No avatar
    bio_length = 0
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/predict/trust" -Method Post -Body $body -ContentType "application/json"
```

**Expected:** Trust Score < 40%, Risk Level = "high"

---

## 6. Architecture - Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│                        MLflow Server                             │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │   Experiments   │  │    Registry     │                       │
│  │  - Training     │  │  - Production   │◀────── Load Model     │
│  │  - Metrics      │  │  - Staging      │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
         ▲                        │
         │ Log                    │ Download
         │                        ▼
┌─────────────────┐      ┌─────────────────┐
│  Trainer        │      │  API Server     │
│  Container      │      │  Container      │
│  - Train        │      │  - /predict/*   │◀──── REST Calls
│  - Tune         │      │  - Model Cache  │
│  - Register     │      │                 │
└─────────────────┘      └─────────────────┘
                                 ▲
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────┴────────┐ ┌──────┴──────┐ ┌────────┴────────┐
     │ Spark Streaming │ │  Dashboard  │ │  Batch Layer    │
     │ (Real-time)     │ │  (On-demand)│ │  (Daily)        │
     └─────────────────┘ └─────────────┘ └─────────────────┘
```

---

## 7. Commands Reference

```bash
# Xem models đã đăng ký
docker exec kol-trainer python -c "
import mlflow
mlflow.set_tracking_uri('http://mlflow:5000')
for m in mlflow.search_registered_models():
    print(f'{m.name}: {[v.current_stage for v in m.latest_versions]}')"

# Đăng ký model mới
docker exec kol-trainer python -m models.registry.register_trust_models

# Test API
curl -X POST http://localhost:8000/predict/trust \
  -H "Content-Type: application/json" \
  -d '{"kol_id":"test","followers_count":10000,...}'

# Xem model info
curl http://localhost:8000/predict/trust/model-info
```

---

## 8. Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `mlflow 404` | Version mismatch | Pin `mlflow==2.9.2` trong requirements |
| `No module lightgbm` | Thiếu package | `pip install lightgbm` |
| `libgomp.so.1 not found` | Thiếu system lib | `apt-get install libgomp1` |
| Score ngược | Label interpretation sai | `trust = 1 - model.predict()` |

---

*Document version: 1.0 - 27/11/2025*

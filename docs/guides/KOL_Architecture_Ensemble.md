
# 🧠 KOL Trustworthiness & Success (Real-Time) – Architecture & Ensemble Plan

## 1️⃣ Lộ trình khởi động (Day-0 → Day-7)

### Day-0/1 – Quy ước & dữ liệu
- Chuẩn hóa **event schema** (click, view, add_to_cart, purchase, post_metrics…)
- Quy ước **ID**: `kol_id`, `campaign_id`, `user_id(anon)`, `event_time(UTC)`
- Quy ước **topic Kafka**: `events.social.raw`, `events.web.raw`, `events.tx.raw`, `features.stream`, `alerts.stream`
- Chuẩn **time partition**: `yyyy/mm/dd/HH` (đồng bộ giữa lake & DWH)
- Chọn **storage**: S3/MinIO (lake) + Iceberg/Hive Metastore; **real-time store**: Cassandra (timeseries) + Redis (cache)

### Day-2/3 – Pipeline tối thiểu chạy được
- Ingestion: connectors/API → **Kafka**
- **Spark Structured Streaming** (micro-batch ~1s) → tính rolling metrics 5–15 phút → đẩy **Cassandra**
- Batch ETL: Spark Batch (nightly) → feature store (parquet/Iceberg)
- Dashboard tạm (Grafana/Kibana) + **FastAPI** (REST) hiển thị KOL metrics

### Day-4/5 – Mô hình baseline + phục vụ
- Trustworthiness v0: **XGBoost** trên feature bảng (ratio follower nghi vấn, burst-like, velocity…), kèm **Isolation Forest** cho outlier
- Success v0: **Prophet** (ngắn hạn 1–24h) + **LightGBM** (lag features) → dự báo click/orders
- **MLflow** tracking + Model Registry; deploy inference qua **FastAPI**

### Day-6/7 – Ensemble + cảnh báo
- Stacking meta-learner **Logistic Regression (calibrated)** gộp:
  - (A) Trustworthiness (XGB)
  - (B) Anomaly score (IForest)
  - (C) Nội dung/sentiment (PhoBERT mBERT nhẹ)
- Rule real-time (Redis Pub/Sub): “follower +5% trong 1h” → alert; “sentiment xấu tăng 3h liên tiếp” → alert

---

## 2️⃣ Chiến lược Ensemble (nhẹ GPU, dễ vận hành)

### Trustworthiness (0–100)
| Layer | Mô hình | Mục tiêu |
|-------|----------|----------|
| Base | XGBoost | Đặc trưng hành vi tổng hợp |
| Base | Isolation Forest | Dị thường tăng trưởng / tương tác |
| Base | PhoBERT/mBERT | Sentiment và spam detection |
| Meta | Logistic Regression | Gộp và chuẩn hóa xác suất đáng tin |

### Success (click → purchase)
| Layer | Mô hình | Mục tiêu |
|-------|----------|----------|
| Base | Prophet | Dự báo trend và mùa vụ |
| Base | LightGBM | Dự báo phi tuyến qua lag features |
| Base | LSTM (tùy GPU) | Học dependency dài hạn |
| Meta | Ridge Regression | Gộp yhat và chuẩn hóa |

### Real-time anomaly (speed layer)
- Rules + EWMA/Z-score nhanh tại stream
- IForest deploy online
- NLP toxicity chạy batch → cập nhật điểm trust

---

## 3️⃣ Kiến trúc thư mục

```bash
kol-platform/
├─ infra/
│  ├─ docker-compose.yml
│  ├─ k8s/
│  └─ terraform/
├─ ingestion/
│  ├─ social_connectors/
│  ├─ web_tracking/
│  └─ schemas/
├─ streaming/
│  ├─ spark_jobs/
│  │  ├─ features_stream.py
│  │  └─ anomaly_rules.py
│  └─ flink_jobs/
├─ batch/
│  ├─ etl/
│  ├─ feature_store/
│  └─ schedules/
├─ models/
│  ├─ trust/
│  ├─ success/
│  ├─ nlp/
│  └─ registry/
├─ serving/
│  ├─ api/
│  └─ dashboard/
├─ dwh/
│  ├─ ddl/
│  └─ queries/
├─ monitoring/
│  ├─ grafana/
│  ├─ prometheus/
│  └─ alerts/
└─ docs/
   ├─ ADRs/
   ├─ API.md
   └─ MODELS.md
```

---

## 4️⃣ Vai trò vắn tắt của từng thành phần

| Thành phần | Vai trò chính |
|-------------|---------------|
| Kafka | Hàng đợi sự kiện (append-only, fault-tolerant) |
| Spark Streaming | Xử lý micro-batch, tính feature real-time |
| Spark Batch | ETL full-history, huấn luyện model |
| S3/MinIO + Iceberg | Data lake (schema evolution, versioning) |
| Cassandra | Time-series real-time metrics |
| Redis | Cache, pub/sub cảnh báo |
| FastAPI | Cung cấp API & inference |
| React/Grafana | Dashboard trực quan |
| Airflow | Lịch batch jobs & train pipeline |
| MLflow | Tracking + model registry |
| Prometheus/Grafana | Monitor latency, throughput |

---

## 5️⃣ Ensemble Deployment (pseudo-code)

```python
# trust ensemble
p_xgb = xgb_clf.predict_proba(X)[:,1]
a_if  = iforest.score_samples(X_if)
s_nlp = sentiment_pos_ratio

meta_X = np.column_stack([p_xgb, a_if, s_nlp])
p_trust = calib_logreg.predict_proba(meta_X)[:,1]
trust_score = (p_trust * 100).round(1)

# success forecast blend
y_prophet = prophet.predict(future)['yhat'].values
y_lgbm    = lgbm.predict(X_lag)
y_blend   = ridge.predict(np.column_stack([y_prophet, y_lgbm]))
```

---

## 6️⃣ Quality gates & cảnh báo

| Rule | Mô tả |
|------|-------|
| Follower spike | >4σ trong 60 phút |
| Sentiment drop | xấu tăng 3h liên tiếp |
| Forecast gap | Giảm >30% so baseline ngành |
| Drift alert | Feature distribution thay đổi >20% |

---

## 7️⃣ Docker Compose (rút gọn)

```yaml
services:
  zookeeper: { image: bitnami/zookeeper:latest }
  kafka:     { image: bitnami/kafka:latest, depends_on: [zookeeper] }
  cassandra: { image: cassandra:5 }
  redis:     { image: redis:7 }
  api:
    build: ./serving/api
    env_file: .env
    depends_on: [kafka, cassandra, redis]
```

---

> ⚙️ **Gợi ý Copilot prompt mở đầu**:  
> “Read the project structure and ensemble plan below. Generate code scaffolding for each component (ingestion, streaming, batch, models, api).  
> Follow the structure and naming convention exactly as in the architecture markdown.”



---

## 8️⃣ Model Architecture – Trust & Success (Batch vs Streaming)

> **Không bắt buộc tuần tự.** Trust và Success **tách bạch**, có thể **chạy song song**, chia sẻ **Feature Layer** và hợp nhất ở **Fusion/Serving**.

### 8.1 Sơ đồ tổng thể (dễ hình dung)

```
[Feature Layer]  -->  [Model Layer]                 -->  [Fusion/Serving]
  |                    |                                  |
  |                    |                                  └─> API / Dashboard / Alerts
  |                    ├─ TRUST: XGBoost + IForest + NLP  (calibrated)
  |                    └─ SUCCESS: Prophet + LightGBM (+ LSTM) → blend
  └─ Kafka / S3 / Iceberg (lag/rolling, velocity, sentiment_ratio, commerce KPIs)
```

- **Feature Layer**: ETL & Streaming build chung các feature (lag/rolling, velocity, burst, pos/neg ratio…).
- **Model Layer**: Hai nhánh **độc lập** – TRUST & SUCCESS – train/infer tách rời.
- **Fusion/Serving**: Gộp output (score, yhat) + **business rules** để ra quyết định cuối.

---

### 8.2 Huấn luyện (Batch, theo lịch Airflow)

```
[00:05] Build features (full history đến H-1)
   ├─[00:40] Train TRUST  (XGB + IForest + NLP  → Logistic Regression (calibrated))
   └─[00:40] Train SUCCESS(Prophet + LightGBM (+ LSTM) → Ridge/ElasticNet blend)
[01:30] Register models → MLflow Registry (versioned)
```

- Chạy **song song** sau khi feature store đã sẵn sàng.
- **Tuần tự mềm (optional):** nếu muốn đưa `Trust_score_t-1` làm **feature** của SUCCESS, thì sắp Trust-train **trước** Success-train trong cùng chu kỳ.
- **Chống leakage:** dùng **Trust_score_t-1** (giờ/ngày trước) khi huấn luyện/predict cho thời điểm **t**.

---

### 8.3 Suy luận (Streaming/Online)

```
Kafka → Spark Streaming
  ├─ Build rolling features (5–15′) → Cassandra/Redis
  ├─ Inference TRUST   (load vX.Y từ MLflow)
  ├─ Inference SUCCESS (load vA.B từ MLflow)
  └─ Fusion = combine(TRUST, SUCCESS, Rules) → API/Dashboard/Alerts
```

- TRUST và SUCCESS **update với nhịp khác nhau** (ví dụ Trust 5–15′; Success 1–5′).
- **Fusion** dùng bản **mới nhất sẵn có** của mỗi nhánh; nếu Trust chưa kịp update, dùng **EMA** (mượt hóa) bản gần nhất.

---

### 8.4 Ba kiểu “quan hệ” giữa TRUST & SUCCESS

**(A) Song song – gộp ở cuối (khuyến nghị cho MVP)**
- Không phụ thuộc tuần tự.
- Ví dụ công thức hợp nhất:
  - `FinalScore = sigmoid(w1*Success + w2*Trust + w3*Sentiment + bias)`
  - `EV (Expected Value) = Success_yhat_revenue * (Trust_score/100)`

**(B) Gating (Trust làm cổng)**
- Nếu `Trust < τ` → giảm trọng số Success hoặc **chặn** recommend/chi tiêu.

**(C) Feature-level coupling (Trust là feature của Success)**
- Dùng `Trust_score_t-1` trong vector feature của SUCCESS.
- Yêu cầu canh mốc thời gian chuẩn để **tránh leakage**.

---

### 8.5 Nhịp cập nhật & Data contract

- **Trust_update:** mỗi **5–15 phút** (cần tổng hợp nhiều tín hiệu: follower, sentiment, burst)
- **Success_update:** mỗi **1–5 phút** (forecast ngắn hạn click/orders)
- **Fusion_update:** mỗi **1 phút**, lấy bản **mới nhất** từ hai nhánh + **EMA** nếu thiếu đồng bộ.

---

### 8.6 Fusion & Business rules (ví dụ)

```
score_final = α * normalize(success_yhat_revenue_next_1h)
            + β * normalize(trust_score)
            + γ * normalize(sentiment_pos_ratio)
            - δ * anomaly_penalty
```
- **α** nhấn vào lợi nhuận gần hạn; **β** bảo vệ rủi ro; **γ** phản ánh “khí hậu dư luận”; **δ** phạt spike bất thường.
- Tinh chỉnh (α,β,γ,δ) bằng **backtest** (rolling split) +/hoặc **Bayesian optimization**.

---

### 8.7 Pseudo-code minh họa

```python
# TRUST (stacking + calibration)
p_xgb = xgb_clf.predict_proba(X_trust)[:, 1]
a_if  = normalize01(-iforest.score_samples(X_if))  # chuyển về [0,1], cao = bất thường
s_nlp = features["sentiment_pos_ratio"]

meta_X = np.column_stack([p_xgb, a_if, s_nlp])
p_trust = calib_logreg.predict_proba(meta_X)[:, 1]
trust_score = (p_trust * 100).round(1)

# SUCCESS (blend)
y_prophet = prophet.predict(future_df)["yhat"].values
y_lgbm    = lgbm.predict(X_lag)
y_blend   = ridge.predict(np.column_stack([y_prophet, y_lgbm]))  # + y_lstm nếu có

# FUSION (điểm xếp hạng/EV)
final_score = sigmoid(w1*y_blend + w2*(trust_score/100) + w3*sentiment_ratio + b)
expected_value = y_blend * (trust_score/100)
```

---

### 8.8 Monitoring & Alerts (model-aware)

- **Calibration check (Trust):** Brier score ≤ ngưỡng; reliability plot mỗi tuần.
- **Drift (features):** PSI/KL-divergence > threshold → trigger retrain.
- **Forecast error (Success):** sMAPE/RMSLE theo rolling window; nếu vượt ngưỡng → degrade sang baseline Prophet.
- **Real-time alerts:**
  - Follower spike > 4σ/60′
  - Sentiment_neg tăng liên tiếp 3h
  - Forecast drop > 30% vs industry baseline

---

### 8.9 Quy tắc triển khai (CI/CD & rollback)

- **MLflow Registry**: chỉ deploy `Stage=Production` đã qua backtest & canary.
- **Blue/Green**: API phục vụ song song vX và vY; route 10% traffic → vY, nếu ổn → 100%.
- **Rollback**: 1 click hạ cấp về phiên bản ổn định trước đó.

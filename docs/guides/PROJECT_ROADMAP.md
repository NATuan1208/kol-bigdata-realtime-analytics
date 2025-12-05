# 🚀 KOL Platform — Project Completion Roadmap & Next Steps

## 📋 Tổng Quan

Tài liệu này cung cấp lộ trình chi tiết để hoàn thành dự án KOL Big Data Analytics Platform, bao gồm:
- Các thành phần đã được thiết lập
- Các thành phần cần triển khai
- Thứ tự ưu tiên và timeline đề xuất
- Best practices cho từng component

---

## ✅ Đã Hoàn Thành

### 1. Infrastructure Setup ✓
- ✅ Docker Compose cho Base Platform (MinIO, Trino, Airflow, PostgreSQL)
- ✅ Docker Compose cho KOL Stack (Kafka, Flink, Spark, MLflow, Cassandra, Redis)
- ✅ Dockerfiles cho Trainer và API services
- ✅ Environment configuration files (.env.base, .env.kol)
- ✅ Makefile với các lệnh quản lý infrastructure
- ✅ Initialization scripts (PostgreSQL, Cassandra, Kafka topics)
- ✅ Trino catalog configuration
- ✅ Comprehensive documentation

### 2. Project Structure ✓
- ✅ Cấu trúc thư mục hoàn chỉnh
- ✅ Separation of concerns (ingestion, streaming, batch, models, serving)
- ✅ Clear architecture documentation

---

## 🔨 Cần Triển Khai

### Phase 1: Foundation & Data Pipeline (Tuần 1-2)

#### 1.1. Ingestion Layer 🔴 CRITICAL
**Priority**: HIGH | **Complexity**: MEDIUM

```
ingestion/
├── social_connectors/
│   ├── __init__.py
│   ├── weibo_scraper.py
│   ├── youtube_api.py
│   └── tiktok_scraper.py
├── web_tracking/
│   ├── __init__.py
│   ├── pixel_tracker.py
│   └── event_collector.py
└── schemas/
    ├── __init__.py
    ├── event_schema.py
    └── validation.py
```

**Tasks**:
- [ ] Implement base connector interface
- [ ] Create Weibo/YouTube/TikTok connectors (chọn 1-2 để MVP)
- [ ] Define Kafka event schemas (Avro/Protobuf)
- [ ] Implement schema validation
- [ ] Write to Kafka topics (`events.social.raw`, `events.web.raw`)
- [ ] Add error handling and retry logic
- [ ] Unit tests cho connectors

**Deliverables**:
- Working data ingestion from at least 1 social platform
- Data flowing into Kafka topics
- Schema Registry configured

**Code Example**:
```python
# ingestion/social_connectors/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Iterator

class BaseSocialConnector(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        pass
    
    @abstractmethod
    def fetch_posts(self, kol_id: str, limit: int = 100) -> Iterator[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def fetch_profile(self, kol_id: str) -> Dict[str, Any]:
        pass
```

---

#### 1.2. Streaming Jobs — Flink (Hot Path) 🔴 CRITICAL
**Priority**: HIGH | **Complexity**: HIGH

```
streaming/flink_jobs/
├── __init__.py
├── windowed_aggregation.py
├── realtime_scoring.py
├── anomaly_detection.py
└── utils/
    ├── kafka_source.py
    ├── cassandra_sink.py
    └── watermark_strategy.py
```

**Tasks**:
- [ ] Setup Flink Table API / DataStream API
- [ ] Implement Kafka source với event-time watermarks
- [ ] Windowed aggregations (5-15 min tumbling/sliding windows):
  - CTR, CVR, engagement rate
  - Follower velocity
  - Sentiment ratio
- [ ] Real-time scoring integration (call ML API)
- [ ] CEP patterns cho anomaly detection:
  - Follower spike > 4σ
  - Sentiment drop 3h liên tiếp
- [ ] Cassandra sink (exactly-once với checkpoint)
- [ ] Redis sink cho features cache
- [ ] Monitoring metrics (Prometheus)

**Deliverables**:
- Working Flink job processing Kafka events
- Real-time metrics written to Cassandra
- Features cached in Redis
- Alerts published to `alerts.stream` topic

**Code Example**:
```python
# streaming/flink_jobs/windowed_aggregation.py
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment

def create_windowed_metrics_job():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.enable_checkpointing(60000)  # 60s
    
    t_env = StreamTableEnvironment.create(env)
    
    # Source: Kafka
    t_env.execute_sql("""
        CREATE TABLE events_raw (
            kol_id STRING,
            event_type STRING,
            event_time TIMESTAMP(3),
            payload ROW<impressions BIGINT, clicks BIGINT>,
            WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'events.social.raw',
            'properties.bootstrap.servers' = 'redpanda:9092',
            'format' = 'avro'
        )
    """)
    
    # Windowed aggregation
    result = t_env.sql_query("""
        SELECT 
            kol_id,
            TUMBLE_START(event_time, INTERVAL '5' MINUTE) as window_start,
            SUM(payload.impressions) as total_impressions,
            SUM(payload.clicks) as total_clicks,
            CAST(SUM(payload.clicks) AS DOUBLE) / SUM(payload.impressions) as ctr
        FROM events_raw
        GROUP BY kol_id, TUMBLE(event_time, INTERVAL '5' MINUTE)
    """)
    
    # Sink: Cassandra
    t_env.execute_sql("""
        CREATE TABLE metrics_cassandra (
            kol_id STRING,
            bucket_ts TIMESTAMP(3),
            total_impressions BIGINT,
            total_clicks BIGINT,
            ctr DOUBLE
        ) WITH (
            'connector' = 'cassandra',
            'host' = 'cassandra',
            'keyspace' = 'kol_metrics',
            'table' = 'kol_realtime_metrics'
        )
    """)
    
    result.execute_insert("metrics_cassandra").wait()
```

---

#### 1.3. Batch ETL — Spark (Cold Path) 🟡 MEDIUM
**Priority**: MEDIUM | **Complexity**: MEDIUM

```
batch/etl/
├── __init__.py
├── bronze_to_silver.py
├── silver_to_gold.py
└── utils/
    ├── spark_session.py
    ├── iceberg_writer.py
    └── schema_evolution.py
```

**Tasks**:
- [ ] Setup Spark session with Iceberg support
- [ ] Bronze layer: ingest from Kafka (replay), write to Iceberg
- [ ] Silver layer: deduplication, data quality, enrichment
- [ ] Gold layer: business aggregations (daily/weekly KPIs)
- [ ] Partitioning strategy (dt, kol_id)
- [ ] Compaction and maintenance jobs
- [ ] Airflow DAGs for scheduling

**Deliverables**:
- Automated nightly ETL pipeline
- Iceberg tables in bronze/silver/gold layers
- Queryable via Trino

**Code Example**:
```python
# batch/etl/bronze_to_silver.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, date_format

def create_silver_tables(spark: SparkSession, date: str):
    # Read from bronze
    bronze_df = spark.read \
        .format("iceberg") \
        .load("lakehouse.bronze.raw_events") \
        .filter(col("dt") == date)
    
    # Deduplicate
    silver_df = bronze_df \
        .dropDuplicates(["event_id"]) \
        .withColumn("processed_at", to_timestamp(col("event_time"))) \
        .select("kol_id", "event_type", "processed_at", "payload")
    
    # Write to silver
    silver_df.write \
        .format("iceberg") \
        .mode("append") \
        .partitionBy("dt") \
        .save("lakehouse.silver.clean_events")
```

---

### Phase 2: ML Models & Training (Tuần 3-4)

#### 2.1. Trust Model 🔴 CRITICAL
**Priority**: HIGH | **Complexity**: HIGH

```
models/trust/
├── __init__.py
├── train_xgb.py
├── train_iforest.py
├── stack_calibrate.py
└── utils/
    ├── feature_engineering.py
    ├── evaluation.py
    └── mlflow_utils.py
```

**Tasks**:
- [ ] Feature engineering từ Silver tables:
  - Follower growth velocity
  - Engagement rate (likes/comments/shares per follower)
  - Burst detection (sudden spikes)
  - Follower/following ratio
  - Account age, verification status
- [ ] Train XGBoost classifier (fraud detection):
  - Target: `is_fake` (labeled data hoặc synthetic)
  - Features: 20-30 features từ behavior patterns
- [ ] Train Isolation Forest (anomaly score)
- [ ] NLP sentiment analysis (PhoBERT/mBERT):
  - Positive/negative comment ratio
  - Spam detection
- [ ] Stacking ensemble với Logistic Regression
- [ ] Calibration (Platt scaling / Isotonic)
- [ ] MLflow experiment tracking
- [ ] Register model to MLflow Registry

**Deliverables**:
- Trained trust model với AUC > 0.80
- Model registered in MLflow (stage: Staging)
- Evaluation report (Brier score, reliability plot)

**Code Example**:
```python
# models/trust/train_xgb.py
import mlflow
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV

def train_trust_model(X_train, y_train, X_val, y_val):
    with mlflow.start_run(run_name="trust-xgb-v1"):
        # Log params
        mlflow.log_param("model_type", "xgboost")
        mlflow.log_param("objective", "binary:logistic")
        
        # Train
        model = xgb.XGBClassifier(
            max_depth=6,
            learning_rate=0.1,
            n_estimators=100,
            objective="binary:logistic"
        )
        model.fit(X_train, y_train)
        
        # Calibrate
        calibrated = CalibratedClassifierCV(model, method='isotonic', cv=5)
        calibrated.fit(X_val, y_val)
        
        # Evaluate
        from sklearn.metrics import roc_auc_score, brier_score_loss
        y_pred_proba = calibrated.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, y_pred_proba)
        brier = brier_score_loss(y_val, y_pred_proba)
        
        mlflow.log_metric("auc", auc)
        mlflow.log_metric("brier_score", brier)
        
        # Save model
        mlflow.sklearn.log_model(calibrated, "trust_model")
        
        return calibrated
```

---

#### 2.2. Success Model 🟡 MEDIUM
**Priority**: MEDIUM | **Complexity**: MEDIUM

```
models/success/
├── __init__.py
├── train_prophet.py
├── train_lgbm.py
├── blend_forecast.py
└── utils/
    ├── time_series_features.py
    └── evaluation.py
```

**Tasks**:
- [ ] Time-series features:
  - Lag features (1h, 6h, 24h, 7d)
  - Rolling means (7d, 14d, 30d)
  - Trend, seasonality decomposition
  - Campaign metadata (budget, category)
- [ ] Train Prophet (trend + seasonality)
- [ ] Train LightGBM (non-linear patterns)
- [ ] Blend với Ridge Regression
- [ ] Backtest với rolling window
- [ ] MLflow experiment tracking
- [ ] Register model

**Deliverables**:
- Trained success model với sMAPE < 15%
- Forecast horizon: 1-24 hours ahead
- Model registered in MLflow

---

#### 2.3. NLP Sentiment Analysis 🟢 LOW
**Priority**: LOW | **Complexity**: MEDIUM

```
models/nlp/
├── __init__.py
├── fine_tune_phobert.py
├── infer_sentiment.py
└── utils/
    └── preprocessing.py
```

**Tasks**:
- [ ] Load pre-trained PhoBERT/mBERT
- [ ] Fine-tune on Vietnamese sentiment dataset (optional)
- [ ] Batch inference on comments/posts
- [ ] Calculate sentiment_pos_ratio feature
- [ ] Integrate vào Trust model

**Deliverables**:
- Sentiment inference pipeline
- Feature added to trust model training

---

### Phase 3: Serving & API (Tuần 5)

#### 3.1. Inference API 🔴 CRITICAL
**Priority**: HIGH | **Complexity**: MEDIUM

```
serving/api/
├── main.py
├── routers/
│   ├── kol.py
│   ├── forecast.py
│   └── health.py
├── services/
│   ├── model_loader.py
│   ├── cassandra_client.py
│   ├── redis_client.py
│   └── feature_fetcher.py
└── schemas/
    ├── request.py
    └── response.py
```

**Tasks**:
- [ ] Implement model loader (MLflow Registry)
- [ ] Feature fetcher (Redis → Cassandra → Trino fallback)
- [ ] Endpoints:
  - `POST /kol/score`: Return trust & success scores
  - `POST /forecast/predict`: Forecast campaign performance
  - `GET /kol/{id}/metrics`: Real-time metrics
  - `GET /rankings`: Top KOLs by score
- [ ] Caching strategy (Redis, 5-min TTL)
- [ ] Rate limiting (100 req/min)
- [ ] Authentication (API token)
- [ ] Error handling & monitoring

**Deliverables**:
- Working REST API
- Swagger documentation (FastAPI auto-generated)
- < 100ms P95 latency

**Code Example**:
```python
# serving/api/routers/kol.py
from fastapi import APIRouter, Depends
from ..services.model_loader import ModelLoader
from ..services.feature_fetcher import FeatureFetcher
from ..schemas.request import ScoreRequest
from ..schemas.response import ScoreResponse

router = APIRouter()

@router.post("/score", response_model=ScoreResponse)
async def score_kol(
    request: ScoreRequest,
    model_loader: ModelLoader = Depends(),
    feature_fetcher: FeatureFetcher = Depends()
):
    # Fetch features
    features = await feature_fetcher.get_kol_features(request.kol_id)
    
    # Load models
    trust_model = model_loader.get_model("kol-trust-ensemble", stage="Production")
    success_model = model_loader.get_model("kol-success-blend", stage="Production")
    
    # Predict
    trust_score = trust_model.predict_proba([features])[0, 1] * 100
    success_forecast = success_model.predict([features])[0]
    
    return ScoreResponse(
        kol_id=request.kol_id,
        trust_score=trust_score,
        success_forecast=success_forecast,
        timestamp=datetime.utcnow()
    )
```

---

#### 3.2. Dashboard (Optional) 🟢 LOW
**Priority**: LOW | **Complexity**: MEDIUM

```
serving/dashboard/
├── app.py
├── components/
│   ├── kol_rankings.py
│   ├── trust_distribution.py
│   └── campaign_performance.py
└── utils/
    └── api_client.py
```

**Options**:
- Streamlit (quickest)
- Grafana dashboards (với Trino datasource)
- React + Recharts (production-ready)

**Tasks**:
- [ ] KOL rankings table
- [ ] Trust score distribution
- [ ] Real-time metrics charts
- [ ] Campaign performance trends

---

### Phase 4: Monitoring & Ops (Tuần 6)

#### 4.1. Observability 🟡 MEDIUM
**Priority**: MEDIUM | **Complexity**: LOW

```
monitoring/
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   ├── dashboards/
│   │   ├── kafka_lag.json
│   │   ├── flink_metrics.json
│   │   └── api_performance.json
│   └── datasources/
│       └── prometheus.yml
└── alerts/
    └── alert_rules.yml
```

**Tasks**:
- [ ] Enable Prometheus exporters:
  - Kafka (Redpanda metrics endpoint)
  - Flink metrics
  - API metrics (prometheus-client)
- [ ] Grafana dashboards:
  - Kafka lag
  - Flink checkpoint duration
  - API latency (P50, P95, P99)
  - Model prediction distribution
- [ ] Alerting rules:
  - High Kafka lag (> 10k messages)
  - Flink job failure
  - API error rate > 5%

---

#### 4.2. CI/CD (Optional) 🟢 LOW
**Priority**: LOW | **Complexity**: MEDIUM

**Tasks**:
- [ ] GitHub Actions workflow:
  - Lint & test on PR
  - Build Docker images
  - Deploy to staging
- [ ] Model versioning workflow:
  - Train → Validate → Register → Deploy
- [ ] Canary deployment strategy

---

## 📅 Timeline Đề Xuất

### Tuần 1-2: Foundation
- ✅ Infrastructure setup (COMPLETED)
- [ ] Ingestion connectors (1 platform)
- [ ] Flink hot path (basic windowing)
- [ ] Spark cold path (bronze → silver)

### Tuần 3-4: ML Models
- [ ] Trust model (XGBoost + IForest)
- [ ] Success model (Prophet + LightGBM)
- [ ] MLflow integration
- [ ] Model evaluation

### Tuần 5: Serving
- [ ] Inference API
- [ ] Feature fetcher
- [ ] Caching & optimization
- [ ] API testing

### Tuần 6: Integration & Testing
- [ ] End-to-end testing
- [ ] Monitoring setup
- [ ] Documentation
- [ ] Demo preparation

---

## 🎯 Success Criteria (MVP)

### Must Have
- ✅ Infrastructure running (base + KOL stack)
- [ ] Data ingestion từ ít nhất 1 social platform
- [ ] Real-time metrics trong Cassandra (latency < 30s)
- [ ] Trust model trained & deployed (AUC > 0.75)
- [ ] Success model trained & deployed (sMAPE < 20%)
- [ ] Working API với 3 core endpoints
- [ ] Basic monitoring (logs + health checks)

### Nice to Have
- [ ] NLP sentiment analysis
- [ ] Anomaly detection với CEP
- [ ] Grafana dashboards
- [ ] Dashboard UI
- [ ] CI/CD pipeline

---

## 🔧 Development Workflow

### Local Development

```powershell
# 1. Start infrastructure
make up-kol

# 2. Develop in container
make exec-trainer  # hoặc exec-api

# 3. Run tests
make test

# 4. Check logs
make logs-trainer
```

### Model Training Workflow

```powershell
# 1. Prepare data (Spark batch job)
docker exec kol-trainer python -m batch.feature_store.build_features

# 2. Train trust model
docker exec kol-trainer python -m models.trust.train_xgb

# 3. Train success model
docker exec kol-trainer python -m models.success.train_lgbm

# 4. Register to MLflow
# (automatic via training scripts)

# 5. Deploy to API
# Update model stage to "Production" in MLflow UI
# API auto-reloads every 5 minutes
```

### Debugging Tips

```powershell
# Check Kafka topics
docker exec kol-redpanda rpk topic list

# Consume messages
docker exec kol-redpanda rpk topic consume events.social.raw --num 10

# Query Cassandra
docker exec kol-cassandra cqlsh -e "SELECT * FROM kol_metrics.kol_realtime_metrics LIMIT 10;"

# Check Redis cache
docker exec kol-redis redis-cli KEYS '*'

# Query Trino
docker exec base-trino trino --execute "SELECT * FROM iceberg.silver.clean_events LIMIT 10;"
```

---

## 📚 Learning Resources

### Flink
- [Flink Table API Tutorial](https://nightlies.apache.org/flink/flink-docs-release-1.18/docs/dev/table/overview/)
- [Event Time & Watermarks](https://nightlies.apache.org/flink/flink-docs-release-1.18/docs/concepts/time/)
- [Exactly-Once Semantics](https://flink.apache.org/2018/02/28/an-overview-of-end-to-end-exactly-once-processing-in-apache-flink-with-apache-kafka-too/)

### Iceberg
- [Apache Iceberg Docs](https://iceberg.apache.org/docs/latest/)
- [Spark + Iceberg Guide](https://iceberg.apache.org/docs/latest/spark-writes/)

### MLflow
- [MLflow Tracking](https://mlflow.org/docs/latest/tracking.html)
- [Model Registry](https://mlflow.org/docs/latest/model-registry.html)

### FastAPI
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- [Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)

---

## 🚨 Risks & Mitigation

### Risk 1: Data Availability
**Problem**: Không có dữ liệu thật từ social platforms
**Mitigation**: 
- Tạo synthetic data generator
- Sử dụng public datasets (YouTube trending, Twitter datasets)
- Mock API responses

### Risk 2: Model Performance
**Problem**: Model accuracy không đạt target
**Mitigation**:
- Start với simpler baseline models
- Focus on feature engineering
- Ensemble multiple approaches
- Tune hyperparameters systematically

### Risk 3: Latency Issues
**Problem**: Real-time scoring > 100ms
**Mitigation**:
- Implement aggressive caching (Redis)
- Pre-compute features where possible
- Optimize model inference (ONNX, quantization)
- Use async API calls

### Risk 4: Infrastructure Complexity
**Problem**: Too many moving parts, hard to debug
**Mitigation**:
- Start simple: use existing docker-compose.yml first
- Migrate gradually to new stack
- Comprehensive logging
- Health checks for all services

---

## 📞 Support & Next Actions

### Immediate Next Steps (This Week)
1. **Test infrastructure**: `make up-kol` và verify all services healthy
2. **Create synthetic data generator**: Mock social media events
3. **Implement first Flink job**: Simple windowed aggregation
4. **Setup MLflow**: Create experiments and test model logging

### Questions to Answer
- [ ] Nguồn dữ liệu thật nào có thể truy cập được?
- [ ] Có labeled data cho trust model không?
- [ ] Yêu cầu về latency và throughput cụ thể?
- [ ] Timeline presentation/demo?

### Resources Needed
- Access to social media APIs (optional)
- Sample datasets
- GPU for training (optional, can use CPU)
- Production deployment target (cloud/on-prem)

---

**Good luck với project! 🎉**

Nếu có câu hỏi hoặc cần support, đừng ngần ngại hỏi thêm!

# 🌈 KOL Real‑Time Analytics — Trustworthiness & Success  
### Spark Structured Streaming for Unified Processing 🚀

> **Mục tiêu chiến lược**  
> Xây nền tảng phân tích & dự đoán **hiệu suất KOL/Campaign theo thời gian thực**.  
> - **Spark Structured Streaming:** xử lý streaming real-time với micro-batch, exactly‑once semantics.
> - **Spark Batch:** ETL/CTAS, backfill lịch sử, chuẩn hoá Lakehouse (Iceberg) cho BI & huấn luyện ML.  
> - **Unified Engine:** Cùng một Spark cluster cho cả streaming và batch → đơn giản hơn, dễ vận hành.
> - Trọng tâm: **Event‑time**, **Exactly‑Once**, **Data Contracts**, **Tách OLTP/OLAP**.

---

## ⚠️ IMPORTANT: Domain Separation

**KOL Analytics** and **SME Pulse** are **TWO INDEPENDENT PROJECTS** that share the same local infrastructure instance for development efficiency. They maintain **STRICT LOGICAL SEPARATION** through:

- 🗂️ **Separate MinIO buckets:** `kol-bronze`, `kol-silver`, `kol-gold` (vs `sme-*`)
- 🗄️ **Separate PostgreSQL databases:** `kol_mlflow`, `kol_metadata` (vs `sme_*`)
- 🚀 **Separate Trino schemas:** `iceberg.kol_*` (vs `iceberg.sme_*`)
- 🧪 **Separate MLflow experiments:** `KOL_*` prefix (vs `SME_*`)

**📖 Read the full explanation:** [Domain Separation Architecture](docs/DOMAIN_SEPARATION.md)

This setup allows both projects to run efficiently on the same laptop while maintaining complete data and pipeline isolation. In production, each project would run on separate infrastructure.

---

## 🚀 Quick Start

**New to the project?** Start here:
1. 📖 [**RUN_INFRASTRUCTURE.md**](RUN_INFRASTRUCTURE.md) — **HƯỚNG DẪN CHẠY HẠ TẦNG** (bắt đầu từ đây!)
2. 📖 [Quick Start Guide](QUICKSTART.md) — Detailed setup guide
3. 🏗️ [Infrastructure Documentation](INFRASTRUCTURE.md) — Architecture and operations
4. 🗺️ [Project Roadmap](PROJECT_ROADMAP.md) — Implementation plan and next steps

**Already familiar?** Jump straight to:
```powershell
make up-kol  # Start everything
make health  # Verify all services
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[DOMAIN_SEPARATION.md](docs/DOMAIN_SEPARATION.md)** | 🏢 **Domain separation philosophy** - How SME & KOL share infra |
| **[RUN_INFRASTRUCTURE.md](RUN_INFRASTRUCTURE.md)** | 🇻🇳 **HƯỚNG DẪN CHẠY HẠ TẦNG** (Vietnamese) - Start here! |
| **[QUICKSTART.md](QUICKSTART.md)** | 5-minute setup guide for first-time users |
| **[INFRASTRUCTURE.md](INFRASTRUCTURE.md)** | Complete infrastructure documentation, service details, troubleshooting |
| **[PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)** | Development roadmap, implementation priorities, timelines |
| **[KOL_Architecture_Ensemble.md](KOL_Architecture_Ensemble.md)** | Detailed architecture and ML ensemble strategy |

---

## 🏗️ Infrastructure Stack

### Base Platform (SME Pulse — Reusable)
- **MinIO**: S3-compatible data lake (bronze/silver/gold layers)
- **Trino**: Distributed SQL query engine for Iceberg tables
- **Hive Metastore**: Iceberg catalog backed by PostgreSQL
- **PostgreSQL**: Metadata storage (Hive, Airflow, MLflow)
- **Apache Airflow**: Workflow orchestration
- **dbt**: SQL transformation framework

### KOL Extensions
- **Redpanda**: Kafka-compatible streaming platform (simpler than Kafka+Zookeeper)
- **Apache Spark**: Unified processing engine for both streaming and batch
  - **Spark Structured Streaming**: Real-time micro-batch processing (1-10s intervals)
  - **Spark Batch**: ETL, backfill, Iceberg CTAS operations
- **MLflow**: Experiment tracking, model registry, artifact storage
- **Cassandra**: Time-series metrics storage
- **Redis**: Feature cache, pub/sub alerts
- **Trainer Service**: ML model training (Trust & Success models)
- **Inference API**: FastAPI model serving with caching

---

## 🌐 Access Points

Once running (`make up-kol`), access services at:

| Service | URL | Purpose |
|---------|-----|---------|
| MinIO Console | http://localhost:9001 | S3-compatible storage UI |
| Trino UI | http://localhost:8080 | SQL query interface |
| Airflow | http://localhost:8081 | Workflow management |
| Redpanda Console | http://localhost:8082 | Kafka topics & messages |
| Spark Master | http://localhost:8084 | Spark cluster & streaming jobs |
| Spark History | http://localhost:18080 | Spark job history |
| MLflow | http://localhost:5000 | Experiment tracking |
| API Docs | http://localhost:8080/docs | Interactive API documentation |
| Jupyter Lab | http://localhost:8888 | Ad-hoc analysis |

---

## ⚡ Quick Commands

```powershell
# Infrastructure
make up-kol          # Start everything (base + KOL)
make up-base         # Start only base platform
make down-all        # Stop everything
make health          # Check all services
make ps-all          # Show service status

# Logs
make logs-kol        # All KOL services
make logs-api        # API only
make logs-spark      # Spark only

# Development
make exec-api        # Shell into API container
make exec-trainer    # Shell into trainer container
make train           # Run training job
make test            # Run tests

# Utilities
make init            # Initialize env files
make clean           # Stop and remove volumes
```

Full command reference: `make help`

---

## 🧭 Core Principles (Nguyên tắc cốt lõi)

1. **⏱️ Event‑Time + Watermarks (Flink)**: ưu tiên thời gian sự kiện, xử lý trễ/out‑of‑order chính xác.  
2. **🧮 Exactly‑Once E2E (Kafka → Flink → Iceberg)**: checkpoint, stateful ops, transactional sink.  
3. **📜 Data Contracts**: Schema Registry + Iceberg **Schema Evolution** (thêm cột an toàn, time‑travel).  
4. **🧩 Tách OLTP/OLAP**: PostgreSQL cho app/metadata/RLS; OLAP trên Iceberg + Trino.  

---

## 🗺️ Overall Architecture (Flink Hot + Spark Cold)

```mermaid
flowchart LR
  %% === Phase 1 ===
  subgraph P1[📥 Ingestion & Messaging]
    direction LR
    S[🛰️ Social APIs<br/>💼 CRM/Ads] --> KAF[(🧩 Apache Kafka)]
    CDC[🔄 Debezium CDC (opt.)] --> KAF
    SR[(📜 Schema Registry)] <--> KAF
  end

  %% === Phase 2 ===
  subgraph P2[⚙️ Processing]
    direction TB

    %% HOT PATH
    subgraph HOT[🔥 Hot Path — Flink (Realtime)]
      direction TB
      KAF --> FJOB[🧠 Flink Jobs<br/><i>Table API/SQL • CEP • Event‑time</i>]
      FJOB --> A[🔔 Alerts]
      FJOB --> FS[(⚡ Online Feature Store<br/>Redis/PG)]
      FJOB --> MS[🤖 Model Serving API<br/>FastAPI/gRPC]
      FJOB --> ICE_S[🧊 Iceberg Sink (Silver)]
    end

    %% COLD PATH
    subgraph COLD[❄️ Cold Path — Spark (Batch)]
      direction TB
      KAF --> SPARK[🟠 Apache Spark (Batch)<br/><i>ETL • CTAS • Backfill</i>]
      SPARK --> M[🗄️ MinIO (S3)] --> I[🗂️ Apache Iceberg<br/><i>Bronze • Silver • Gold</i>]
      KAF --> KC[🔌 Kafka Connect (opt.)] --> M
    end
  end

  %% === Phase 3 ===
  subgraph P3[📊 Consumption & MLOps]
    direction TB
    I --> T[🚀 Trino] --> BI[📊 Metabase/Superset]
    I --> NB[🧪 Notebooks]
    I --> TRN[🏋️ Batch Training (Spark/Notebooks)]
    TRN --> MR[(📦 Model Registry)] --> MS
    PG[(🗃️ PostgreSQL OLTP<br/><i>Metadata • RLS</i>)]
  end
```

> **Legend**: 🔥 Flink (Hot) • ❄️ Spark (Cold) • 🧩 Kafka • 🧠 Flink • 🟠 Spark • 🧊 Iceberg • 🗄️ MinIO • 🚀 Trino • 📊 BI • 🗃️ PostgreSQL • 🤖 Model Serving • ⚡ Feature Store • 📜 Contracts

---

## 🔥 Hot Path — Flink (Realtime, ms–s)

```mermaid
flowchart TD
  A[🧩 Kafka Source] --> W{⏱️ Watermarks<br/><i>Event‑time</i>}
  W --> S1[🧪 Stateless]
  S1 --> ST{🧠 Stateful}
  ST -- Windows --> MET[📈 KPIs Windowed]
  ST -- CEP --> CEP[🧭 Pattern Detection]

  subgraph ENR[🧩 Enrichment & Scoring]
    L[⚡ Lookup Features (Redis/PG)] --> CALL[🤖 Model API]
    CALL --> SC[✅ Trust/Success Score]
  end

  MET --> L
  CEP --> L

  SC --> OUT{🚚 Sinks}
  OUT -- 🔔 --> AL[Alerts]
  OUT -- ⚡ --> FSW[Feature Write‑back]
  OUT -- 🧊 --> ICE[Iceberg (Silver)]
```

**Key notes**
- **Exactly‑once** (Kafka→Flink→Iceberg), checkpoint 30–60s, savepoint trước deploy.  
- **Latency mục tiêu**: ingest < **1s**, alert < **30s**.  

---

## ❄️ Cold Path — Spark (Batch, min–hours)

```mermaid
flowchart LR
  KR[🧩 Kafka (Replay)] --> SP[🟠 Spark Batch<br/><i>ETL • CTAS • Backfill</i>]
  SP --> M[🗄️ MinIO (S3)]
  M --> I[🗂️ Apache Iceberg<br/><i>Bronze • Silver • Gold</i>]
  I --> T[🚀 Trino] --> BI[📊 BI Dashboards]
```

**Best practices**
- **Partition**: `dt`, `creator_id`/`campaign_id`; **compact** file nhỏ; **snapshot cleanup**.  
- **Spark** đảm nhiệm: chuẩn hoá, dedupe, aggregate; **CTAS** để sinh bảng Gold phục vụ BI.  

---

## 🧰 Tooling & Vai trò theo giai đoạn

| Hạng mục | Công cụ | Vai trò & Lý do chọn |
|---|---|---|
| Ingestion | **Kafka**, **Debezium** | Bus chịu tải cao, replay; CDC từ DB/CRM nếu cần |
| Contracts | **Schema Registry** | Buộc schema, thay đổi **backward-compatible** |
| Hot Path | **Flink** | Event‑time, stateful windows, **CEP**, exactly‑once |
| Cold Path | **Spark (Batch)** | ETL/CTAS, backfill, optimize/compact Iceberg |
| Lakehouse | **MinIO + Iceberg** | Lưu trữ + ACID table format, schema evolution |
| Query | **Trino** | SQL trên Iceberg cho BI/Ad‑hoc/Exploration |
| OLTP | **PostgreSQL (RLS)** | Metadata, config, multi‑tenant cho backend |
| Features | **Redis/PG** | Online/Offline feature store |
| Serving | **FastAPI/gRPC** | Model microservice, A/B test, circuit breaker |
| BI | **Metabase/Superset** | Dashboard KPI, cohort/attribution |
| Obs. | **Prometheus/Grafana** | Kafka lag, Flink metrics, API SLIs |

---

## 🎯 Mục tiêu & KPIs

- **Realtime**: ingest < **1s**, alert < **30s**, dashboard < **1m**.  
- **Tính toàn vẹn**: exactly‑once; không double‑count.  
- **BI**: truy vấn KPI 30 ngày < **10s** qua Trino.  
- **Ops**: savepoint trước deploy; rollback < **5 phút**.  

---

## 🧪 ML & Feedback Loop

- **Training (Batch/Spark/Notebooks)** đọc Iceberg (Silver/Gold); log & registry; deploy ra **Model API**.  
- **Realtime scoring** gọi từ Flink; write‑back features & inference logs vào Iceberg → **vòng lặp học**.  

---

## ✅ Checklist triển khai

- [ ] Kafka topics có key (`creator_id`/`brand_id`) + Schema Registry active.  
- [ ] Flink jobs bật checkpoint + exactly‑once; savepoint trước deploy.  
- [ ] Spark ETL có **CTAS**/optimize + compact định kỳ; Iceberg partition hợp lý.  
- [ ] Trino catalog hoạt động; BI dashboards render ngon.  
- [ ] Observability: Grafana hiển thị lag/checkpoint/API error; alert không spam.  

---

## 🔐 Bảo mật

- **RLS** trên PostgreSQL; **IAM**/policy MinIO; secrets qua Vault/SSM; tách **prod/staging**.  

> **TL;DR**: **Flink** nắm luồng **nóng** để quyết định **tức thì**; **Spark** xử lý **lạnh** để chuẩn hoá dữ liệu cho **BI & training** — tất cả dựa trên **Kafka + Iceberg + Trino** với contracts & quan sát chặt chẽ.

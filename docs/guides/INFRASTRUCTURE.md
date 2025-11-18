# 🏗️ KOL Big Data Analytics — Infrastructure Documentation

## 📋 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Design](#infrastructure-design)
3. [Quick Start](#quick-start)
4. [Service Details](#service-details)
5. [Data Flow](#data-flow)
6. [Operations Guide](#operations-guide)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Architecture Overview

The KOL Big Data Analytics platform is designed as a **layered architecture** that reuses a shared base platform (SME Pulse) and extends it with KOL-specific services.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    KOL PROJECT LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Redpanda     │  │ Flink        │  │ Spark        │          │
│  │ (Streaming)  │  │ (Hot Path)   │  │ (Cold Path)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ MLflow       │  │ Trainer      │  │ API          │          │
│  │ (ML Ops)     │  │ (Training)   │  │ (Serving)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ Cassandra    │  │ Redis        │                             │
│  │ (Time Series)│  │ (Cache)      │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BASE PLATFORM LAYER (SME Pulse)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ MinIO        │  │ Trino        │  │ Airflow      │          │
│  │ (Data Lake)  │  │ (Query)      │  │ (Orchestrate)│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ PostgreSQL   │  │ Hive Meta    │  │ dbt          │          │
│  │ (Metadata)   │  │ (Catalog)    │  │ (Transform)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ▼
                    data-platform-net (Docker Network)
```

### Key Principles

1. **⏱️ Event-Time Processing**: Flink handles real-time streaming with watermarks
2. **🧮 Exactly-Once Semantics**: End-to-end consistency from Kafka → Flink → Iceberg
3. **📜 Data Contracts**: Schema Registry ensures data quality
4. **🧩 Separation of Concerns**: OLTP (PostgreSQL) vs OLAP (Iceberg/Trino)
5. **🔄 Lambda Architecture**: Hot path (Flink) + Cold path (Spark)

---

## 🏗️ Infrastructure Design

### Why This Design?

#### Base Platform Reuse (SME Pulse)
- **MinIO**: S3-compatible object storage for lakehouse (bronze/silver/gold layers)
- **Iceberg + Hive Metastore**: ACID transactions, schema evolution, time travel
- **Trino**: Distributed SQL queries across data lake
- **PostgreSQL**: Centralized metadata storage (Hive, Airflow, MLflow)
- **Airflow**: Workflow orchestration for batch jobs
- **dbt**: SQL-based data transformation

#### KOL-Specific Extensions

##### Streaming Layer
- **Redpanda** (chosen over Kafka+Zookeeper):
  - ✅ Simpler: Single binary, no Zookeeper dependency
  - ✅ Kafka API-compatible
  - ✅ Built-in Schema Registry
  - ✅ Better performance, lower latency
  - ✅ Easier to operate

##### Stream Processing
- **Apache Flink** (Hot Path — Real-time):
  - ✅ True streaming (not micro-batch)
  - ✅ Event-time semantics + Watermarks
  - ✅ Exactly-once guarantees
  - ✅ Complex Event Processing (CEP)
  - ✅ Low latency (milliseconds to seconds)
  - ✅ Rich state management
  - **Use Cases**: Real-time scoring, anomaly detection, alerts

- **Apache Spark** (Cold Path — Batch):
  - ✅ Mature ecosystem
  - ✅ Excellent for ETL and CTAS operations
  - ✅ Iceberg integration
  - ✅ Better for backfill and historical analysis
  - **Use Cases**: Batch ETL, feature engineering, model training

##### ML Operations
- **MLflow**: Experiment tracking, model registry, artifact storage (MinIO)
- **Trainer Service**: Batch/online training jobs (XGBoost, Prophet, LightGBM, NLP)
- **Inference API**: FastAPI serving champion models with caching

##### Data Storage
- **Cassandra**: Time-series metrics (windowed aggregations, real-time KPIs)
- **Redis**: Feature cache, pub/sub for alerts, session storage

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop with at least **8GB RAM** and **4 CPU cores**
- Docker Compose V2
- 20GB free disk space
- Windows: WSL2 backend recommended

### Step 1: Clone and Setup

```powershell
# Clone the repository
cd "d:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\Bigdata_IE212\DoAn\kol-platform"

# Initialize environment files
make init

# Edit environment files as needed
notepad .env.base
notepad .env.kol
```

### Step 2: Create Docker Network

```powershell
make network-create
```

### Step 3: Start Base Platform

```powershell
# Start MinIO, PostgreSQL, Trino, Airflow, Hive Metastore
make up-base

# Wait for services to be healthy (2-3 minutes)
# Check status
make ps-base
```

**Access Points (Base Platform):**
- MinIO Console: http://localhost:9001 (minioadmin / minioadmin123)
- Trino UI: http://localhost:8080 (user: trino)
- Airflow UI: http://localhost:8081 (admin / admin123)
- PostgreSQL: `localhost:5432` (admin / admin123)

### Step 4: Start KOL Stack

```powershell
# Start KOL-specific services on top of base
make up-kol

# Wait for services to initialize (3-5 minutes)
# Check status
make ps-kol
```

**Access Points (KOL Stack):**
- Redpanda Console: http://localhost:8082 (Kafka UI)
- Flink JobManager: http://localhost:8083
- Spark Master UI: http://localhost:8084
- MLflow UI: http://localhost:5000
- Inference API: http://localhost:8080
- Jupyter Lab: http://localhost:8888

### Step 5: Verify Installation

```powershell
# Check health of all services
make health

# View logs
make logs-kol

# Test API
curl http://localhost:8080/healthz
```

### Step 6: Initialize Data Infrastructure

```powershell
# Initialize MinIO buckets
make init-buckets

# Initialize Kafka topics
make init-topics

# Initialize database schemas
make init-db
```

---

## 🔧 Service Details

### Base Platform Services

#### MinIO (Data Lake)
- **Port**: 9000 (API), 9001 (Console)
- **Buckets**: `bronze`, `silver`, `gold`, `mlflow`, `lakehouse`, `dbt`
- **Access**: S3-compatible API
- **Use**: Raw data ingestion, Iceberg table storage, MLflow artifacts

#### PostgreSQL (Metadata DB)
- **Port**: 5432
- **Databases**: `metastore`, `airflow`, `mlflow`
- **Use**: Hive Metastore backend, Airflow metadata, MLflow tracking

#### Hive Metastore (Catalog)
- **Port**: 9083 (Thrift)
- **Use**: Iceberg table catalog, schema registry

#### Trino (Query Engine)
- **Port**: 8080
- **Catalogs**: `iceberg`, `postgres`
- **Use**: SQL queries on Iceberg tables, BI dashboards

#### Airflow (Orchestration)
- **Port**: 8081
- **Components**: Webserver, Scheduler
- **Use**: Schedule batch ETL, training jobs, maintenance tasks

### KOL Stack Services

#### Redpanda (Streaming Platform)
- **Ports**: 
  - 19092: Kafka API (external)
  - 18081: Schema Registry
  - 8082: Console UI
- **Topics**: `events.social.raw`, `events.web.raw`, `events.tx.raw`, `features.stream`, `alerts.stream`, `metrics.windowed`
- **Use**: Event streaming, message bus

#### Flink (Hot Path Stream Processing)
- **Ports**: 
  - 8083: JobManager UI
  - 6123: RPC
- **Components**: JobManager (1), TaskManager (2)
- **Features**: 
  - Event-time processing with watermarks
  - Exactly-once semantics
  - 60s checkpointing
  - CEP for pattern detection
- **Use**: Real-time scoring, anomaly detection, windowed aggregations

#### Spark (Cold Path Batch Processing)
- **Ports**: 
  - 7077: Master RPC
  - 8084: Master UI
  - 18080: History Server
- **Components**: Master (1), Worker (2)
- **Use**: Batch ETL, backfill, Iceberg CTAS, feature engineering

#### MLflow (ML Operations)
- **Port**: 5000
- **Backend Store**: PostgreSQL (`mlflow` database)
- **Artifact Store**: MinIO (`s3://mlflow/artifacts`)
- **Features**: Experiment tracking, model registry, artifact versioning
- **Use**: Track experiments, version models, deploy champions

#### Cassandra (Time-Series DB)
- **Port**: 9042 (CQL)
- **Keyspace**: `kol_metrics`
- **Use**: Store real-time windowed metrics, KPI time-series

#### Redis (Cache & Pub/Sub)
- **Port**: 6379
- **Use**: Feature cache, alert pub/sub, session storage

#### Trainer Service (ML Training)
- **Container**: `kol-trainer`
- **Volumes**: `/app/models`, `/app/batch`, `/app/data`
- **Use**: Run training jobs for Trust/Success models
- **Manual Execution**: `make train`

#### Inference API (Model Serving)
- **Port**: 8080
- **Framework**: FastAPI + Uvicorn
- **Workers**: 4
- **Features**: 
  - Load models from MLflow Registry
  - Cache predictions in Redis
  - Rate limiting
  - Health checks
- **Endpoints**: 
  - `GET /healthz`: Health check
  - `POST /kol/score`: Score KOL trustworthiness & success
  - `POST /forecast/predict`: Predict campaign performance

#### Jupyter Lab (Optional)
- **Port**: 8888
- **Volumes**: `/home/jovyan/work` (notebooks), `/home/jovyan/models`
- **Use**: Ad-hoc analysis, model prototyping

---

## 📊 Data Flow

### Ingestion Flow

```
External APIs/Sources
         ↓
   Ingestion Jobs
         ↓
   Kafka Topics (Redpanda)
    ├─→ events.social.raw
    ├─→ events.web.raw
    └─→ events.tx.raw
```

### Hot Path (Real-time)

```
Kafka Topics
    ↓
Flink Jobs (Event-Time Processing)
    ├─→ Windowed Aggregations (5-15 min windows)
    ├─→ Real-time Scoring (Trust/Success)
    ├─→ Anomaly Detection (CEP patterns)
    └─→ Alert Generation
         ↓
    ├─→ Cassandra (windowed metrics)
    ├─→ Redis (features, alerts)
    ├─→ Inference API (real-time scores)
    └─→ Iceberg Silver (for replay/audit)
```

### Cold Path (Batch)

```
Kafka Topics (replay/backfill)
    ↓
Spark Batch Jobs (Airflow scheduled)
    ├─→ Bronze Layer (raw, deduplicated)
    ├─→ Silver Layer (cleaned, enriched)
    └─→ Gold Layer (aggregated, business metrics)
         ↓
    Iceberg Tables on MinIO
         ↓
    Trino (SQL queries)
         ↓
    BI Dashboards / Notebooks
```

### ML Training Flow

```
Iceberg Tables (Silver/Gold)
    ↓
Trainer Service
    ├─→ Feature Engineering
    ├─→ Model Training
    │   ├─ Trust: XGBoost + IForest + NLP
    │   └─ Success: Prophet + LightGBM
    ├─→ Ensemble Stacking
    └─→ Calibration
         ↓
    MLflow (experiment tracking)
         ↓
    Model Registry (versioning)
         ↓
    Champion Model → Inference API
```

### Inference Flow

```
API Request
    ↓
Load Features (Redis cache → Cassandra → Trino)
    ↓
Load Champion Model (MLflow Registry)
    ↓
Predict (Trust Score + Success Forecast)
    ↓
Cache Result (Redis, 5 min TTL)
    ↓
Return Response
```

---

## 🛠️ Operations Guide

### Starting Services

```powershell
# Start everything (base + KOL)
make up-kol

# Start only base platform
make up-base

# Start only KOL services (base must be running)
make up-kol-only
```

### Stopping Services

```powershell
# Stop KOL stack only
make down-kol

# Stop base platform only
make down-base

# Stop everything
make down-all
```

### Viewing Logs

```powershell
# All KOL services
make logs-kol

# Specific service
make logs-api
make logs-trainer
make logs-flink
make logs-spark

# Base platform
make logs-base
```

### Service Status

```powershell
# KOL stack status
make ps-kol

# Base platform status
make ps-base

# All services
make ps-all
```

### Accessing Containers

```powershell
# API container shell
make exec-api

# Trainer container shell
make exec-trainer

# PostgreSQL shell
make exec-postgres

# Redis CLI
make exec-redis

# Cassandra CQL shell
make exec-cassandra
```

### Running Training Jobs

```powershell
# Manual training (all models)
make train

# Train specific model
make train-trust
make train-success

# Or exec into trainer and run directly
docker exec -it kol-trainer python -m models.trust.train_xgb
```

### Rebuilding Services

```powershell
# Rebuild and restart custom services (API, trainer)
make rebuild

# Build only (without restart)
make build
```

### Monitoring

```powershell
# Health check all services
make health

# Docker stats
make stats
```

### Cleanup

```powershell
# Stop and remove containers + volumes
make clean

# Deep clean (including images)
make clean-all
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Services Not Starting

**Symptoms**: Container exits immediately or health checks fail

**Solutions**:
```powershell
# Check logs
make logs-kol

# Check Docker resources
docker system df

# Ensure minimum requirements (8GB RAM, 4 CPU)
docker info

# Restart Docker Desktop
```

#### 2. Network Issues

**Symptoms**: Services can't communicate, connection refused errors

**Solutions**:
```powershell
# Verify network exists
docker network ls | grep data-platform-net

# Recreate network
make network-remove
make network-create

# Restart services
make restart-kol
```

#### 3. MinIO Connection Errors

**Symptoms**: MLflow or Trainer can't access S3/MinIO

**Solutions**:
```powershell
# Check MinIO is running
curl http://localhost:9000/minio/health/live

# Verify credentials in .env files
# Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY match MINIO_ROOT_USER/PASSWORD

# Check bucket initialization
docker logs base-minio-init
```

#### 4. MLflow Model Loading Fails

**Symptoms**: API can't load models, 404 errors

**Solutions**:
```powershell
# Check MLflow is healthy
curl http://localhost:5000/health

# Verify models exist
# Go to http://localhost:5000 and check Model Registry

# Check environment variables in API container
docker exec kol-api env | grep MLFLOW
```

#### 5. Kafka/Redpanda Issues

**Symptoms**: Producers/consumers can't connect

**Solutions**:
```powershell
# Check Redpanda status
docker logs kol-redpanda

# List topics
docker exec kol-redpanda rpk topic list --brokers redpanda:9092

# Recreate topics
make init-topics
```

#### 6. Out of Memory

**Symptoms**: Containers crashing, OOMKilled in logs

**Solutions**:
```powershell
# Increase Docker Desktop memory limit to 12GB+
# Reduce worker replicas in docker-compose.kol.yml
# Reduce Spark/Flink memory settings in .env.kol
```

#### 7. Port Conflicts

**Symptoms**: Error binding to port, address already in use

**Solutions**:
```powershell
# Check what's using the port (example: 8080)
netstat -ano | findstr :8080

# Change port in .env.kol file
# Example: API_PORT=8090

# Restart services
make restart-kol
```

### Debug Commands

```powershell
# Check service health
docker ps --filter health=unhealthy

# Inspect network
docker network inspect data-platform-net

# View resource usage
docker stats --no-stream

# Check disk space
docker system df

# View service dependencies
docker compose -f infra/docker-compose.kol.yml config
```

### Getting Help

1. Check logs: `make logs-kol`
2. Review environment variables in `.env.base` and `.env.kol`
3. Verify all services are healthy: `make health`
4. Check Docker resources: `docker info`
5. Review architecture documentation

---

## 📚 Additional Resources

- [KOL Architecture & Ensemble Plan](../KOL_Architecture_Ensemble.md)
- [README](../README.md)
- [Copilot Tasks](../COPILOT_TASKS.md)

---

## 🔐 Security Considerations

### Production Deployment Checklist

- [ ] Change all default passwords in `.env` files
- [ ] Use secrets management (Docker Secrets, AWS SSM, HashiCorp Vault)
- [ ] Enable TLS/SSL for all external endpoints
- [ ] Configure authentication for Trino, Airflow, MLflow, API
- [ ] Set up network policies and firewalls
- [ ] Enable audit logging
- [ ] Implement Row-Level Security (RLS) in PostgreSQL
- [ ] Use IAM policies for MinIO access
- [ ] Enable Redis password authentication
- [ ] Configure Cassandra authentication
- [ ] Rotate credentials regularly
- [ ] Set up monitoring and alerting (Prometheus + Grafana)

---

*Last Updated: 2025-11-13*

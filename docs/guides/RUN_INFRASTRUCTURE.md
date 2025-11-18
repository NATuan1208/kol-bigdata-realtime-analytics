# 🚀 Hướng Dẫn Chạy Hạ Tầng KOL Platform

## 📋 Tổng Quan

Hệ thống KOL Platform sử dụng **Spark Structured Streaming** cho cả streaming và batch processing, với architecture gồm 2 layers:

### Base Platform Layer (SME Pulse)
- MinIO, PostgreSQL, Trino, Airflow, Hive Metastore, dbt

### KOL Extension Layer
- Redpanda (Kafka), Spark (Streaming + Batch), MLflow, Cassandra, Redis, API

---

## ⚡ Quick Start (5 phút)

### Bước 1: Khởi tạo môi trường

```powershell
# Di chuyển vào thư mục project
cd "d:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\Bigdata_IE212\DoAn\kol-platform"

# Tạo network và environment files
make init
make network-create
```

### Bước 2: Khởi động toàn bộ hệ thống

```powershell
# Khởi động tất cả services (Base + KOL)
make up-kol
```

**Đợi 3-5 phút** để tất cả services khởi động hoàn tất.

### Bước 3: Kiểm tra trạng thái

```powershell
# Kiểm tra health của services
make health

# Xem trạng thái containers
make ps-all

# Xem logs
make logs-kol
```

### Bước 4: Khởi tạo dữ liệu

```powershell
# Tạo MinIO buckets
make init-buckets

# Tạo Kafka topics
make init-topics

# Tạo Cassandra keyspace và tables
docker exec -i kol-cassandra cqlsh < infra/scripts/init-cassandra.cql
```

---

## 🌐 Truy Cập Services

Sau khi khởi động thành công, truy cập các services:

| Service | URL | Thông tin đăng nhập |
|---------|-----|---------------------|
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin123 |
| **Trino UI** | http://localhost:8080 | User: trino (no password) |
| **Airflow** | http://localhost:8081 | admin / admin123 |
| **Redpanda Console** | http://localhost:8082 | Không cần đăng nhập |
| **Spark Master UI** | http://localhost:8084 | Không cần đăng nhập |
| **Spark History** | http://localhost:18080 | Không cần đăng nhập |
| **MLflow UI** | http://localhost:5000 | Không cần đăng nhập |
| **API Swagger** | http://localhost:8080/docs | Không cần đăng nhập (dev) |
| **Jupyter Lab** | http://localhost:8888 | Không cần đăng nhập (dev) |

---

## 🔧 Các Lệnh Thường Dùng

### Quản lý Infrastructure

```powershell
# Khởi động
make up-kol          # Khởi động tất cả (Base + KOL)
make up-base         # Chỉ khởi động Base platform
make up-kol-only     # Chỉ khởi động KOL stack (giả sử Base đã chạy)

# Dừng
make down-kol        # Dừng KOL stack
make down-base       # Dừng Base platform
make down-all        # Dừng tất cả

# Khởi động lại
make restart-kol     # Khởi động lại KOL stack
```

### Xem Logs

```powershell
# Tất cả KOL services
make logs-kol

# Service cụ thể
make logs-api
make logs-trainer
make logs-spark

# Base platform
make logs-base
```

### Truy cập Containers

```powershell
# API container
make exec-api

# Trainer container
make exec-trainer

# PostgreSQL shell
make exec-postgres

# Redis CLI
make exec-redis

# Cassandra CQL shell
make exec-cassandra
```

### Chạy Training Jobs

```powershell
# Chạy training tất cả models
make train

# Chạy training model cụ thể
make train-trust
make train-success

# Hoặc exec vào container và chạy trực tiếp
docker exec -it kol-trainer python -m models.trust.train_xgb
```

---

## 🚀 Chạy Spark Structured Streaming Jobs

### Cách 1: Submit job từ container

```powershell
# Exec vào Spark streaming container
docker exec -it kol-spark-streaming bash

# Submit Spark Structured Streaming job
spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.datastax.spark:spark-cassandra-connector_2.12:3.4.1 \
    /opt/spark-jobs/features_stream.py
```

### Cách 2: Submit từ host machine

```powershell
# Submit job vào Spark cluster
docker exec kol-spark-streaming spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.datastax.spark:spark-cassandra-connector_2.12:3.4.1 \
    /opt/spark-jobs/features_stream.py
```

### Monitor Streaming Job

- **Spark UI**: http://localhost:8084 (xem Streaming tab)
- **Logs**: `docker logs -f kol-spark-streaming`
- **Console output**: Metrics được in ra console khi chạy

---

## 🔍 Khám Phá Dữ Liệu

### Query với Trino

```powershell
# Mở Trino CLI
docker exec -it base-trino trino

# List catalogs
SHOW CATALOGS;

# List schemas trong Iceberg
SHOW SCHEMAS FROM iceberg;

# Tạo test table
CREATE TABLE iceberg.silver.test_events (
    kol_id VARCHAR,
    event_type VARCHAR,
    event_time TIMESTAMP,
    impressions BIGINT
);
```

### Kiểm tra Kafka Topics

```powershell
# List topics
docker exec kol-redpanda rpk topic list

# Produce test message
docker exec -it kol-redpanda rpk topic produce events.social.raw
# Nhập JSON message, ví dụ:
# {"kol_id":"kol_001","event_type":"impression","event_time":"2025-11-13T10:00:00Z","impressions":100}

# Consume messages
docker exec kol-redpanda rpk topic consume events.social.raw --num 10
```

### Query Cassandra

```powershell
# Mở CQL shell
docker exec -it kol-cassandra cqlsh

# Use keyspace
USE kol_metrics;

# Describe tables
DESCRIBE TABLES;

# Query realtime metrics
SELECT * FROM kol_realtime_metrics LIMIT 10;

# Query với điều kiện
SELECT * FROM kol_realtime_metrics WHERE kol_id = 'kol_001' LIMIT 10;
```

### Kiểm tra Redis Cache

```powershell
# Mở Redis CLI
docker exec -it kol-redis redis-cli

# List all keys
KEYS *

# Get value
GET some_key

# Monitor real-time commands
MONITOR
```

---

## 🧪 Test API

### Health Check

```powershell
# PowerShell
Invoke-WebRequest http://localhost:8080/healthz

# hoặc dùng curl (nếu có WSL)
curl http://localhost:8080/healthz
```

### API Documentation

Mở browser và vào: **http://localhost:8080/docs**

Đây là Swagger UI interactive, có thể test tất cả endpoints.

---

## 🐛 Troubleshooting

### Services không khởi động?

```powershell
# Kiểm tra logs
make logs-kol

# Kiểm tra Docker resources
docker info

# Đảm bảo có ít nhất 8GB RAM allocated cho Docker

# Khởi động lại Docker Desktop
```

### Port conflicts?

```powershell
# Kiểm tra port đang dùng (ví dụ 8080)
netstat -ano | findstr :8080

# Sửa port trong .env.kol
notepad .env.kol
# Thay đổi API_PORT=8090

# Khởi động lại
make restart-kol
```

### Network issues?

```powershell
# Kiểm tra network
docker network ls | findstr data-platform-net

# Recreate network
make network-remove
make network-create

# Khởi động lại services
make restart-kol
```

### Out of memory?

1. Tăng Docker Desktop memory lên 12GB+
2. Giảm số worker replicas trong `docker-compose.kol.yml`
3. Giảm Spark worker memory trong `.env.kol`

---

## 📊 Monitoring

### Kiểm tra trạng thái services

```powershell
# Health check tất cả
make health

# Xem resource usage
make stats
# hoặc
docker stats --no-stream
```

### Xem Spark UI

- **Master UI**: http://localhost:8084
  - Workers status
  - Running applications
  - Completed applications
  
- **Streaming Query Progress**: Check trong Spark UI > Streaming tab

### Xem MLflow Experiments

- **MLflow UI**: http://localhost:5000
  - Experiments list
  - Model registry
  - Artifacts

---

## 🛑 Dừng và Cleanup

### Dừng services

```powershell
# Dừng KOL stack (giữ Base platform)
make down-kol

# Dừng tất cả
make down-all
```

### Cleanup (xóa volumes)

```powershell
# Cleanup containers và volumes
make clean

# Deep clean (bao gồm images)
make clean-all
```

**⚠️ Cảnh báo**: `make clean` sẽ xóa tất cả dữ liệu trong volumes!

---

## 📚 Tài Liệu Chi Tiết

| Document | Mô tả |
|----------|-------|
| **[QUICKSTART.md](QUICKSTART.md)** | Quick start guide chi tiết |
| **[INFRASTRUCTURE.md](INFRASTRUCTURE.md)** | Tài liệu infrastructure đầy đủ |
| **[PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)** | Lộ trình triển khai project |
| **[README.md](README.md)** | Tổng quan project |

---

## 🎯 Next Steps

Sau khi chạy được infrastructure:

1. **Implement Ingestion**: Tạo connectors để ingest data từ social platforms
2. **Develop Streaming Jobs**: Implement Spark Structured Streaming jobs
3. **Train Models**: Train Trust & Success models
4. **Build API**: Hoàn thiện Inference API
5. **Create Dashboard**: Tạo UI cho monitoring và visualization

Chi tiết xem trong: **[PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)**

---

## 🆘 Hỗ Trợ

Nếu gặp vấn đề:

1. Kiểm tra logs: `make logs-kol`
2. Xem health status: `make health`
3. Review troubleshooting section trong **[INFRASTRUCTURE.md](INFRASTRUCTURE.md)**
4. Check Docker resources: `docker info`

---

**Chúc bạn thành công với project! 🎉**

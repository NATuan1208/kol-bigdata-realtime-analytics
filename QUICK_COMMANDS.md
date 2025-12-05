# Quick Command Reference — KOL Platform (Shared Infrastructure)

## 🚀 Daily Workflow

### 1. Start Everything
```bash
# Prerequisite: Ensure SME Pulse is running first
# Then:
cd /path/to/kol-platform
make check-sme    # Verify SME Pulse is ready
make up-kol       # Start KOL services
```

### 2. Check Status
```bash
make ps-kol       # Show KOL services status
docker ps         # Show all running containers
```

### 3. View Logs
```bash
make logs-kol         # All KOL services
make logs-api         # API only
make logs-trainer     # Trainer only
make logs-spark       # Spark only
make logs-redpanda    # Redpanda only
```

### 4. Stop Services
```bash
make down-kol     # Stop KOL (SME Pulse keeps running)
```

---

## 🕷️ TikTok Scraper - Parallel Workers (Recommended)

### 🚀 One-Click Start: Full Platform
```powershell
# Start toàn bộ platform (Spark Streaming + Scrapers + Metrics Refresh)
.\scripts\start_full_platform.ps1

# Với options
.\scripts\start_full_platform.ps1 -NoComments -NoProducts -MaxKols 10
```

Script sẽ:
1. ✅ Check infrastructure (Redis, Kafka, Spark)
2. ✅ Install redis trong Spark containers
3. ✅ Start Spark Streaming job → Redis
4. ✅ Start Discovery Daemon (tìm KOL mới)
5. ✅ Start Video/Comment/Product Workers (delay 240s)
6. ✅ Start Metrics Refresh (tính velocity)

### 🔄 Khởi chạy 5 Workers Song Song
```powershell
# Khởi chạy workers:
# - Discovery Scraper (Default profile) - Tìm KOL mới → push kol.discovery.raw
# - Metrics Refresh - Re-push tracked KOLs để tính velocity
# - Video Stats Worker (Profile 1) - Lấy profile + videos
# - Comment Extractor (Profile 1) - Extract comments
# - Product Extractor (Profile 6) - Extract products
.\scripts\start_parallel_scrapers.ps1

# Chỉ lấy products (không lấy comments)
.\scripts\start_parallel_scrapers.ps1 -NoComments

# Custom settings với 2 intervals riêng biệt
.\scripts\start_parallel_scrapers.ps1 -MaxKols 10 -MaxVideos 30 `
    -DiscoveryInterval 7200 `  # 2 tiếng tìm KOL mới
    -RefreshInterval 300       # 5 phút tính velocity

# Không chạy Metrics Refresh
.\scripts\start_parallel_scrapers.ps1 -NoRefresh
```

### Chạy từng worker riêng (5 terminals)
```powershell
# Terminal 1: Discovery scraper (tìm username mới) - chạy mỗi 2 tiếng
py -m ingestion.sources.kol_scraper daemon --discovery-only --interval 7200

# Terminal 2: Metrics Refresh (tính velocity) - chạy mỗi 5 phút
py -m ingestion.sources.metrics_refresh --interval 300

# Terminal 3: Video Stats Worker (lấy profile + video stats) - delay 240s
py -m ingestion.consumers.video_stats_worker --max-videos 20 --start-delay 240

# Terminal 4: Comment Extractor (lấy comments) - delay 240s
py -m ingestion.consumers.comment_extractor --max-comments 50 --start-delay 240

# Terminal 5: Product Extractor (lấy products từ TikTok Shop) - delay 240s
py -m ingestion.consumers.product_extractor --max-videos 20 --start-delay 240
```

### ⚙️ Intervals và Delays
| Parameter | Default | Mô tả |
|-----------|---------|-------|
| `DiscoveryInterval` | 7200s (2h) | Tần suất tìm KOL mới |
| `RefreshInterval` | 300s (5min) | Tần suất re-push để tính velocity |
| `WorkerDelay` | 240s (4min) | Workers đợi Discovery push messages |

### ⚠️ Reset Kafka Consumer Offset (nếu bị đọc lại message cũ)
```powershell
# Xem offset hiện tại
docker exec -it kol-redpanda rpk group describe kol-video-stats-v3
docker exec -it kol-redpanda rpk group describe kol-comment-extractor-v3
docker exec -it kol-redpanda rpk group describe kol-product-extractor-v3

# Reset về LATEST (chỉ đọc message mới)
docker exec -it kol-redpanda rpk group seek kol-video-stats-v3 --to end
docker exec -it kol-redpanda rpk group seek kol-comment-extractor-v3 --to end
docker exec -it kol-redpanda rpk group seek kol-product-extractor-v3 --to end
```

---

## 📊 Spark ETL Jobs

### Load Kafka → MinIO (Iceberg)
```powershell
# Chạy batch job load data từ Kafka vào MinIO
docker exec kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.2,org.apache.hadoop:hadoop-aws:3.3.4 `
    --conf spark.hadoop.fs.s3a.endpoint=http://sme-minio:9000 `
    --conf spark.hadoop.fs.s3a.access.key=minio `
    --conf spark.hadoop.fs.s3a.secret.key=minio123 `
    --conf spark.hadoop.fs.s3a.path.style.access=true `
    /opt/spark/work-dir/streaming/spark_jobs/kafka_to_iceberg_simple.py --mode batch
```

### Product Tracker (Track sold_count changes)
```powershell
# Dry-run để xem products cần track
python -m batch.feature_store.product_tracker --local --dry-run

# Chạy thật (scrape sold_count mới từ TikTok Shop)
python -m batch.feature_store.product_tracker --local

# Chạy headless (không hiện browser)
python -m batch.feature_store.product_tracker --local --headless

# Chạy trong Docker cluster
docker exec -it kol-spark-master spark-submit `
    --master spark://spark-master:7077 `
    /opt/spark/work-dir/batch/feature_store/product_tracker.py
```

---

## 🕷️ TikTok Scraper - Single Mode (Legacy)

### Chạy nhanh (all defaults)
```powershell
# Daemon mode - chạy liên tục (discovery + profile + videos)
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon

# Chỉ discovery (dùng với parallel workers)
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon --discovery-only

# Chạy 1 lần từng mode
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper discovery
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper full --max-kols 5
```

### Chạy với custom options
```powershell
# Custom interval (mặc định 300s = 5 phút)
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon --interval 600

# Giới hạn số KOL mỗi vòng
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon --max-kols-per-round 10

# Full options
.\.venv\Scripts\python.exe -m ingestion.sources.kol_scraper daemon `
    --interval 300 `
    --max-kols-per-round 20 `
    --discovery-only `
    --kafka-broker localhost:19092
```

---

## 🔧 Network Management

### Create Shared Network (Run Once)
```bash
make network-create
# OR manually:
docker network create sme-network
```

### Inspect Network
```bash
make network-inspect
# Shows all containers connected to sme-network
```

---

## 🏥 Health Checks

### Verify SME Pulse Prerequisites
```bash
make check-sme
```
**Checks:**
- ✅ sme-network exists
- ✅ sme-postgres is running
- ✅ sme-minio is running
- ✅ sme-trino is running
- ✅ sme-hive-metastore is running

### Check Service Health
```bash
# MLflow
curl http://localhost:5000/health

# API
curl http://localhost:8080/healthz

# Redpanda
docker exec kol-redpanda rpk cluster health

# Cassandra
docker exec kol-cassandra cqlsh -e "DESCRIBE CLUSTER"

# Redis
docker exec kol-redis redis-cli ping
```

---

## 🔄 Restart Services

### Restart All KOL
```bash
make restart-kol
```

### Restart Individual Service
```bash
docker compose -f infra/docker-compose.kol.yml restart <service>
# Examples:
docker compose -f infra/docker-compose.kol.yml restart api
docker compose -f infra/docker-compose.kol.yml restart mlflow
docker compose -f infra/docker-compose.kol.yml restart spark-master
```

---

## 🐚 Access Containers

### API Container
```bash
docker exec -it kol-api bash
```

### Trainer Container
```bash
docker exec -it kol-trainer bash
```

### Spark Master
```bash
docker exec -it kol-spark-master bash
```

### Cassandra
```bash
docker exec -it kol-cassandra cqlsh
```

### Redis
```bash
docker exec -it kol-redis redis-cli
```

---

## 🚨 Trending Stream (Realtime hot scores)

This job computes per-KOL velocities and a TrendingScore and writes
results into Redis for dashboards. It is separate from the Iceberg
ingest stream.

### Prerequisites Setup (One-time)
```powershell
# Install redis client inside Spark containers
docker exec -u root kol-spark-master pip install redis
docker exec -u root infra-spark-worker-1 pip install redis
docker exec -u root infra-spark-worker-2 pip install redis

# Verify installation
docker exec kol-spark-master python3 -c "import redis; print('redis OK')"

# Fix Ivy cache permission (nếu gặp permission error)
docker exec -u root kol-spark-master mkdir -p /home/spark/.ivy2
docker exec -u root kol-spark-master chmod -R 777 /home/spark/.ivy2

# Clear old checkpoints (nếu thay đổi schema)
docker exec kol-spark-master rm -rf /tmp/kafka-trending-checkpoint
```

### Run Trending Stream Job
```powershell
# Submit trending job (background)
docker exec -d kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 `
    /opt/spark-jobs/kafka_trending_stream.py
```

### Trending Formula
```
score = ALPHA * view_velocity + BETA * like_velocity + GAMMA * share_velocity

# Defaults:
ALPHA = 1.0   # View weight
BETA = 0.5    # Like weight  
GAMMA = 0.2   # Share weight

# Velocity = current - previous (delta giữa 2 lần scrape)
```

### Check Redis Trending Data
```powershell
# List all tracked KOLs
docker exec kol-redis redis-cli KEYS "streaming_scores:*"

# Get score for specific KOL
docker exec kol-redis redis-cli HGETALL "streaming_scores:xuannhilamgido"

# Sample output:
#  1) "ts"           → timestamp
#  2) "score"        → trending score
#  3) "view"         → total views
#  4) "like"         → total likes
#  5) "share"        → total shares
#  6) "video_count"  → number of videos
#  7) "view_vel"     → view velocity
#  8) "like_vel"     → like velocity
#  9) "share_vel"    → share velocity
```

### Environment variables (optional):
- `REDIS_HOST`, `REDIS_PORT`, `TREND_ALPHA`, `TREND_BETA`, `TREND_GAMMA`


---

## 📊 Access Web UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| MLflow UI | http://localhost:5000 | No auth |
| Inference API | http://localhost:8080 | Token in .env.kol |
| Spark Master UI | http://localhost:8084 | No auth |
| Redpanda Console | http://localhost:8082 | No auth |
| Jupyter Notebook | http://localhost:8888 | Token in .env.kol |
| MinIO Console (SME) | http://localhost:9001 | minioadmin/minioadmin |
| Trino UI (SME) | http://localhost:8080 | No auth |
| Airflow (SME) | http://localhost:8081 | admin/admin |

---

## 🔍 Debugging

### Check Network Connectivity
```bash
# From trainer container
docker exec -it kol-trainer bash
ping sme-postgres
ping sme-minio
ping sme-trino
```

### Test Database Connection
```bash
docker exec -it kol-trainer python -c "
import psycopg2
conn = psycopg2.connect(
    host='sme-postgres',
    port=5432,
    database='mlflow',
    user='admin',
    password='admin'
)
print('✓ Connected to sme-postgres')
conn.close()
"
```

### Test MinIO Connection
```bash
docker exec -it kol-trainer python -c "
import boto3
s3 = boto3.client(
    's3',
    endpoint_url='http://sme-minio:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)
print('✓ Connected to sme-minio')
print('Buckets:', [b['Name'] for b in s3.list_buckets()['Buckets']])
"
```

### View Container Resource Usage
```bash
docker stats
# Shows CPU, memory, network I/O for all containers
```

---

## 🗄️ Database Operations

### Connect to PostgreSQL (SME)
```bash
docker exec -it sme-postgres psql -U admin -d mlflow
```

### Create MLflow Database
```sql
CREATE DATABASE mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO admin;
```

### List Databases
```bash
docker exec -it sme-postgres psql -U admin -c "\l"
```

---

## 📦 MinIO Operations

### List Buckets
```bash
docker exec sme-minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec sme-minio mc ls local/
```

### Create MLflow Bucket
```bash
docker exec sme-minio mc mb local/mlflow
```

### Check Bucket Size
```bash
docker exec sme-minio mc du local/mlflow
```

---

## ☁️ Kafka/Redpanda Operations

### Create Topics (Chạy 1 lần khi setup)
```bash
# Tạo tất cả KOL topics
docker exec kol-redpanda rpk topic create kol.discovery.raw --partitions 4
docker exec kol-redpanda rpk topic create kol.profiles.raw --partitions 4
docker exec kol-redpanda rpk topic create kol.videos.raw --partitions 4
docker exec kol-redpanda rpk topic create kol.comments.raw --partitions 4
docker exec kol-redpanda rpk topic create kol.products.raw --partitions 4
docker exec kol-redpanda rpk topic create kol.scraper.events --partitions 1

# Hoặc chạy 1 lệnh (PowerShell)
@("kol.discovery.raw", "kol.profiles.raw", "kol.videos.raw", "kol.comments.raw", "kol.products.raw") | ForEach-Object { docker exec kol-redpanda rpk topic create $_ --partitions 4 }
```

### List Topics
```bash
docker exec kol-redpanda rpk topic list
```

### Describe Topic
```bash
docker exec kol-redpanda rpk topic describe kol.discovery.raw
docker exec kol-redpanda rpk topic describe kol.profiles.raw
docker exec kol-redpanda rpk topic describe kol.videos.raw
docker exec kol-redpanda rpk topic describe kol.comments.raw
docker exec kol-redpanda rpk topic describe kol.products.raw
```

### View Consumer Groups
```bash
# List all consumer groups
docker exec kol-redpanda rpk group list

# Describe specific group (xem offset, lag)
docker exec kol-redpanda rpk group describe kol-video-stats-v3
docker exec kol-redpanda rpk group describe kol-comment-extractor-v3
docker exec kol-redpanda rpk group describe kol-product-extractor-v3
```

### Reset Consumer Offset
```bash
# Reset về latest (chỉ đọc message mới từ giờ)
docker exec kol-redpanda rpk group seek kol-video-stats-v3 --to end
docker exec kol-redpanda rpk group seek kol-comment-extractor-v3 --to end
docker exec kol-redpanda rpk group seek kol-product-extractor-v3 --to end

# Reset về earliest (đọc lại từ đầu)
docker exec kol-redpanda rpk group seek kol-video-stats-v3 --to start
```

### Produce Test Message
```bash
docker exec -it kol-redpanda rpk topic produce kol.discovery.raw
# Type message, press Ctrl+C to exit
```

### Consume Messages
```bash
docker exec -it kol-redpanda rpk topic consume kol.discovery.raw --offset newest
docker exec -it kol-redpanda rpk topic consume kol.profiles.raw --offset newest
```

---

## ⚡ Spark Operations

### Submit Kafka → MinIO ETL (Batch Mode)
```powershell
docker exec kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.2,org.apache.hadoop:hadoop-aws:3.3.4 `
    --conf spark.hadoop.fs.s3a.endpoint=http://sme-minio:9000 `
    --conf spark.hadoop.fs.s3a.access.key=minio `
    --conf spark.hadoop.fs.s3a.secret.key=minio123 `
    --conf spark.hadoop.fs.s3a.path.style.access=true `
    /opt/spark/work-dir/streaming/spark_jobs/kafka_to_iceberg_simple.py --mode batch
```

### Submit Bronze → Silver ETL
```bash
docker exec kol-spark-master spark-submit \
  --master spark://spark-master:7077 \
  /opt/spark/work-dir/batch/etl/bronze_to_silver.py
```

### Submit Product Tracker Batch Job
```bash
docker exec kol-spark-master spark-submit \
  --master spark://spark-master:7077 \
  /opt/spark/work-dir/batch/feature_store/product_tracker.py
```

### Check Spark UI
```
# Spark Master UI: http://localhost:8084
# Spark History: http://localhost:18080
```

---

## 🤖 Model Training

### Train Trust Model
```bash
docker exec kol-trainer python -m models.trust.train_xgb
```

### Train Success Model
```bash
docker exec kol-trainer python -m models.success.train_lgbm
```

### Register Model in MLflow
```bash
docker exec kol-trainer python -m models.registry.model_versioning
```

---

## 🧪 Testing

### Test API Endpoints
```bash
# Health check
curl http://localhost:8080/healthz

# Get KOL trust score
curl -X POST http://localhost:8080/api/v1/kol/score \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-change-in-production" \
  -d '{
    "kol_id": "kol123",
    "features": {
      "follower_count": 50000,
      "engagement_rate": 0.05,
      "sentiment_score": 0.8
    }
  }'

# Get success forecast
curl -X POST http://localhost:8080/api/v1/forecast/success \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-change-in-production" \
  -d '{
    "kol_id": "kol123",
    "campaign_id": "camp456",
    "horizon_days": 7
  }'
```

---

## 🧹 Cleanup

### Remove All KOL Containers
```bash
make down-kol
```

### Remove Volumes (⚠️ Deletes Data)
```bash
docker compose -f infra/docker-compose.kol.yml down -v
```

### Remove All Stopped Containers
```bash
docker container prune
```

### Remove Unused Images
```bash
docker image prune -a
```

---

## 🆘 Emergency Commands

### Force Restart Everything
```bash
make down-kol
docker system prune -f
make check-sme
make up-kol
```

### View All Logs (Last 100 Lines)
```bash
docker compose -f infra/docker-compose.kol.yml logs --tail=100
```

### Kill All KOL Containers
```bash
docker ps | grep kol- | awk '{print $1}' | xargs docker kill
```

---

## 📚 Help

### Show All Available Commands
```bash
make help
```

### Docker Compose Help
```bash
docker compose --help
docker compose -f infra/docker-compose.kol.yml --help
```

---

## 🔗 Related Documents

- **docs/guides/PARALLEL_SCRAPING_GUIDE.md**: Hướng dẫn chạy parallel scrapers
- **MIGRATION_TO_SHARED_INFRA.md**: Complete migration guide
- **SHARED_INFRASTRUCTURE_GUIDE.md**: Connection architecture
- **QUICKSTART.md**: Step-by-step tutorial
- **Makefile**: All commands (`make help`)

---

## 📋 Workflow Tóm Tắt

### 🚀 Cách 1: One-Click Start (Recommended)
```powershell
# Start toàn bộ platform
.\scripts\start_full_platform.ps1

# Chạy rồi ngồi uống trà 🍵
# Platform sẽ tự động:
# 1. Check infrastructure
# 2. Start Spark Streaming → Redis
# 3. Start Discovery (mỗi 2h tìm KOL mới)
# 4. Start Workers (delay 240s rồi mới chạy)
# 5. Start Metrics Refresh (mỗi 5min tính velocity)
```

### 🔧 Cách 2: Chạy Thủ Công từng Bước

**Bước 1: Start Spark Streaming Job**
```powershell
# Cài redis (1 lần)
docker exec -u root kol-spark-master pip install redis

# Start streaming job
docker exec -d kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 `
    /opt/spark-jobs/kafka_trending_stream.py
```

**Bước 2: Chạy Discovery + 5 Workers Song Song**
```powershell
# Terminal 1: Discovery (mỗi 2 tiếng)
py -m ingestion.sources.kol_scraper daemon --discovery-only --interval 7200

# Terminal 2: Metrics Refresh (mỗi 5 phút)
py -m ingestion.sources.metrics_refresh --interval 300

# Terminal 3: Video Stats (delay 240s)
py -m ingestion.consumers.video_stats_worker --max-videos 20 --start-delay 240

# Terminal 4: Comments (optional)
py -m ingestion.consumers.comment_extractor --max-comments 50 --start-delay 240

# Terminal 5: Products
py -m ingestion.consumers.product_extractor --max-videos 20 --start-delay 240
```

**Bước 3: Monitor**
```powershell
# Check Redis có data
docker exec kol-redis redis-cli KEYS "streaming_scores:*"

# Check Spark UI
http://localhost:8084
```

### 📊 Optional: Chạy Spark ETL (load Kafka → MinIO)
```powershell
docker exec kol-spark-master /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.2,org.apache.hadoop:hadoop-aws:3.3.4 `
    --conf spark.hadoop.fs.s3a.endpoint=http://sme-minio:9000 `
    --conf spark.hadoop.fs.s3a.access.key=minio `
    --conf spark.hadoop.fs.s3a.secret.key=minio123 `
    --conf spark.hadoop.fs.s3a.path.style.access=true `
    /opt/spark/work-dir/streaming/spark_jobs/kafka_to_iceberg_simple.py --mode batch
```

### 📦 Optional: Chạy Product Tracker (track sold_count changes)
```powershell
# Schedule: 2-3 lần/ngày
python -m batch.feature_store.product_tracker --local
```

---

**Tip**: Bookmark this file for quick reference during development! 🚀

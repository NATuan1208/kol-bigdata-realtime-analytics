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

### List Topics
```bash
docker exec kol-redpanda rpk topic list
```

### Describe Topic
```bash
docker exec kol-redpanda rpk topic describe events.social.raw
```

### Produce Test Message
```bash
docker exec -it kol-redpanda rpk topic produce events.social.raw
# Type message, press Ctrl+C to exit
```

### Consume Messages
```bash
docker exec -it kol-redpanda rpk topic consume events.social.raw
```

---

## ⚡ Spark Operations

### Submit Spark Job (Structured Streaming)
```bash
docker exec kol-spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.datastax.spark:spark-cassandra-connector_2.12:3.4.0 \
  /opt/spark-jobs/features_stream.py
```

### Submit Batch ETL Job
```bash
docker exec kol-spark-master spark-submit \
  --master spark://spark-master:7077 \
  /opt/batch/etl/bronze_to_silver.py
```

### Check Spark History
```bash
# Access Spark History Server: http://localhost:18080
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

- **MIGRATION_TO_SHARED_INFRA.md**: Complete migration guide
- **SHARED_INFRASTRUCTURE_GUIDE.md**: Connection architecture
- **QUICKSTART.md**: Step-by-step tutorial
- **Makefile**: All commands (`make help`)

---

**Tip**: Bookmark this file for quick reference during development! 🚀

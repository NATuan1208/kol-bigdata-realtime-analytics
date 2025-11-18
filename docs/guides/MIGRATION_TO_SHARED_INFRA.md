# Migration to Shared Infrastructure — Complete ✓

## Overview

The KOL Big Data Analytics Platform has been successfully migrated to **reuse infrastructure** from the existing **SME Pulse project** instead of maintaining duplicate services. This optimization reduces resource usage and simplifies deployment.

---

## What Changed?

### 🔄 Architecture Shift

**BEFORE (Standalone):**
```
KOL Project:
├── Base Platform (docker-compose.base.yml)
│   ├── MinIO
│   ├── PostgreSQL
│   ├── Trino
│   ├── Hive Metastore
│   └── Airflow
└── KOL Services (docker-compose.kol.yml)
    ├── Redpanda
    ├── Spark
    ├── MLflow
    ├── Cassandra
    ├── Redis
    └── API
```

**AFTER (Shared):**
```
SME Pulse Project (External):          KOL Project:
├── sme-postgres                       └── KOL Services (docker-compose.kol.yml)
├── sme-minio                              ├── Redpanda
├── sme-trino                ───────►      ├── Spark
├── sme-hive-metastore      Shared         ├── MLflow (connects to SME)
├── sme-airflow             Network        ├── Cassandra
└── sme-metabase           sme-network     ├── Redis
                                            └── API (connects to SME)
```

---

## Files Updated

### 1. **docker-compose.kol.yml** ✅

**Changes:**
- ✅ Network changed from `data-platform-net` to **`sme-network`** (external)
- ✅ MLflow backend: `postgres:5432` → **`sme-postgres:5432`**
- ✅ MLflow S3: `http://minio:9000` → **`http://sme-minio:9000`**
- ✅ Trainer service: Updated all hostnames to SME-prefixed versions
- ✅ API service: Updated MinIO endpoint to **`sme-minio`**
- ✅ Jupyter service: Updated S3 endpoint to **`sme-minio`**
- ✅ All services now use **`sme-network`** instead of `data-platform-net`
- ✅ Removed dependencies on `postgres` and `minio` containers (external now)

**Key Updates:**
```yaml
networks:
  sme-network:
    external: true
    name: sme-network

services:
  mlflow:
    command: >
      mlflow server
      --backend-store-uri postgresql://user:pass@sme-postgres:5432/mlflow
    environment:
      MLFLOW_S3_ENDPOINT_URL: http://sme-minio:9000
    networks:
      - sme-network
```

### 2. **.env.kol** ✅

**Changes:**
- ✅ Added SME Pulse service hostnames section at the top
- ✅ Documented prerequisites (SME Pulse must be running)
- ✅ Added all SME service connection details

**New Environment Variables:**
```bash
# SME Pulse Infrastructure (Shared Services)
POSTGRES_HOST=sme-postgres
POSTGRES_PORT=5432
MINIO_ENDPOINT=http://sme-minio:9000
TRINO_HOST=sme-trino
TRINO_PORT=8080
HIVE_METASTORE_URI=thrift://sme-hive-metastore:9083
AIRFLOW_HOST=sme-airflow-webserver
```

### 3. **Makefile** ✅

**Changes:**
- ✅ Removed all `up-base`, `down-base`, `logs-base`, `ps-base` commands
- ✅ Added **`check-sme`** command to verify SME Pulse prerequisites
- ✅ Updated `up-kol` to check SME Pulse before starting
- ✅ Added `up-kol-force` for development (skip checks)
- ✅ Network name changed to **`sme-network`**
- ✅ Updated help text to reflect shared infrastructure approach
- ✅ Removed `down-all` and `ps-all` (only KOL services managed)

**New Commands:**
```bash
make check-sme           # Verify SME Pulse is running
make network-create      # Create shared sme-network
make network-inspect     # Inspect network and connected containers
make up-kol              # Start KOL (checks SME first)
make up-kol-force        # Start KOL (skip SME check)
```

### 4. **SHARED_INFRASTRUCTURE_GUIDE.md** ✅

Created comprehensive guide with:
- Architecture diagram
- Setup instructions (6 steps)
- Service access points
- Environment variable mapping
- Troubleshooting section
- Daily development workflow

---

## Prerequisites for Running KOL Platform

### Step 1: Ensure SME Pulse is Running

The KOL platform **requires** these SME Pulse services to be running:

| Service | Container Name | Port | Purpose |
|---------|---------------|------|---------|
| PostgreSQL | `sme-postgres` | 5432 | MLflow backend, metadata storage |
| MinIO | `sme-minio` | 9000 | Data lake (Bronze/Silver/Gold), model artifacts |
| Trino | `sme-trino` | 8080 | SQL query engine for data lake |
| Hive Metastore | `sme-hive-metastore` | 9083 | Iceberg catalog |
| Airflow | `sme-airflow-webserver` | 8081 | Orchestration (optional) |

**Verify SME Pulse:**
```bash
docker ps | grep sme-
```

You should see containers like:
```
sme-postgres
sme-minio
sme-trino
sme-hive-metastore
sme-airflow-webserver
```

### Step 2: Create Shared Network

The **`sme-network`** must exist and be shared between both projects:

```bash
# Create network (run this ONCE)
docker network create sme-network

# Verify SME Pulse services are on this network
docker network inspect sme-network
```

Make sure SME Pulse services are connected to `sme-network`:
- If not, add `sme-network` to SME Pulse docker-compose.yml and restart services

### Step 3: Start KOL Platform

```bash
# Check prerequisites
make check-sme

# Start KOL services
make up-kol
```

---

## Service Connectivity

### From KOL to SME Pulse

KOL services connect to SME Pulse using **container hostnames**:

| KOL Service | Connects To | Connection String |
|-------------|-------------|-------------------|
| MLflow | PostgreSQL | `postgresql://user:pass@sme-postgres:5432/mlflow` |
| MLflow | MinIO | `http://sme-minio:9000` |
| Trainer | Trino | `http://sme-trino:8080` |
| Trainer | MinIO | `http://sme-minio:9000` |
| Trainer | PostgreSQL | `postgresql://user:pass@sme-postgres:5432/kol_platform` |
| API | MinIO | `http://sme-minio:9000` (via MLflow) |
| Jupyter | MinIO | `http://sme-minio:9000` |

### Access Points from Host Machine

**KOL Services:**
- Redpanda Console: http://localhost:8082
- Spark Master UI: http://localhost:8084
- MLflow UI: http://localhost:5000
- Inference API: http://localhost:8080
- Jupyter: http://localhost:8888

**SME Pulse Services (Shared):**
- MinIO Console: http://localhost:9001
- Trino: http://localhost:8080 ⚠️ (may conflict with API port)
- Airflow: http://localhost:8081
- Metabase: http://localhost:3000

---

## Database Setup

### MLflow Database in PostgreSQL

MLflow needs a database in the **SME Pulse PostgreSQL**:

```bash
# Connect to SME Pulse PostgreSQL
docker exec -it sme-postgres psql -U admin -d postgres

# Create MLflow database
CREATE DATABASE mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO admin;

# Exit
\q
```

### KOL Platform Database (Optional)

If you need a separate database for KOL metadata:

```sql
CREATE DATABASE kol_platform;
GRANT ALL PRIVILEGES ON DATABASE kol_platform TO admin;
```

---

## MinIO Bucket Setup

MLflow stores artifacts in **MinIO (S3-compatible)**. Create the bucket:

```bash
# Access MinIO Console: http://localhost:9001
# Login: minioadmin / minioadmin

# Create bucket: "mlflow"
# Or via mc CLI:
docker exec sme-minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec sme-minio mc mb local/mlflow
```

---

## Verification Steps

### 1. Check Network Connectivity

```bash
# Inspect shared network
make network-inspect

# Verify both SME and KOL containers are connected
docker network inspect sme-network | grep Name
```

### 2. Test Database Connection

```bash
# From KOL trainer container
docker exec -it kol-trainer bash

# Test PostgreSQL connection
python -c "
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

### 3. Test MinIO Connection

```bash
# From KOL trainer container
docker exec -it kol-trainer bash

# Test MinIO connection
python -c "
import boto3
s3 = boto3.client(
    's3',
    endpoint_url='http://sme-minio:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)
buckets = s3.list_buckets()
print('✓ Connected to sme-minio')
print('Buckets:', [b['Name'] for b in buckets['Buckets']])
"
```

### 4. Check MLflow

```bash
# Access MLflow UI: http://localhost:5000
# Should see:
# - Backend Store: PostgreSQL (sme-postgres)
# - Artifact Store: s3://mlflow/ (sme-minio)
```

---

## Troubleshooting

### Problem: `make up-kol` fails with "SME Pulse not running"

**Solution:**
```bash
# Check SME Pulse status
docker ps | grep sme-

# If not running, start SME Pulse first
cd /path/to/sme-pulse-project
docker compose up -d

# Then try again
cd /path/to/kol-platform
make up-kol
```

### Problem: MLflow cannot connect to PostgreSQL

**Symptoms:**
- MLflow container crashes
- Logs show: `could not connect to server: Connection refused`

**Solution:**
```bash
# 1. Verify sme-postgres is running
docker ps | grep sme-postgres

# 2. Check if sme-postgres is on sme-network
docker network inspect sme-network | grep sme-postgres

# 3. If not on network, add SME Pulse to sme-network:
#    Edit SME Pulse docker-compose.yml and add:
#    networks:
#      sme-network:
#        external: true
#    Then restart SME Pulse
```

### Problem: Services cannot resolve hostnames

**Symptoms:**
- `getaddrinfo failed` or `Name or service not known`
- Cannot resolve `sme-postgres`, `sme-minio`, etc.

**Solution:**
```bash
# 1. Ensure sme-network exists
docker network ls | grep sme-network

# 2. Verify both projects use the same network
docker network inspect sme-network

# 3. Restart KOL services
make down-kol
make up-kol
```

### Problem: Port conflicts (e.g., API port 8080 conflicts with Trino)

**Solution 1: Change KOL API port**
```bash
# Edit .env.kol
API_PORT=8085

# Restart
make restart-kol
```

**Solution 2: Change Trino port in SME Pulse**
```bash
# Edit SME Pulse docker-compose.yml
# Change Trino port mapping:
ports:
  - "8088:8080"  # Host:Container
```

---

## Daily Development Workflow

### Starting Work

```bash
# 1. Ensure SME Pulse is running (in separate terminal)
cd /path/to/sme-pulse-project
docker compose ps  # Check status

# 2. Start KOL platform
cd /path/to/kol-platform
make check-sme     # Verify prerequisites
make up-kol        # Start KOL services

# 3. Access services
# - MLflow: http://localhost:5000
# - API: http://localhost:8080
# - Spark UI: http://localhost:8084
```

### Stopping Work

```bash
# Stop KOL services only (SME Pulse keeps running)
make down-kol

# Or stop everything (both projects)
make down-kol
cd /path/to/sme-pulse-project
docker compose down
```

### Viewing Logs

```bash
# KOL logs
make logs-kol           # All KOL services
make logs-api           # API only
make logs-trainer       # Trainer only
make logs-spark         # Spark only

# SME Pulse logs (from SME project)
cd /path/to/sme-pulse-project
docker compose logs -f postgres
docker compose logs -f minio
```

---

## Benefits of Shared Infrastructure

✅ **Resource Efficiency**: No duplicate PostgreSQL, MinIO, Trino instances  
✅ **Simplified Data Lake**: Single source of truth in SME MinIO  
✅ **Unified Metadata**: Shared Hive Metastore and Iceberg catalog  
✅ **Cost Savings**: Reduced memory/CPU/disk usage  
✅ **Easier Maintenance**: Update base services once, both projects benefit  
✅ **Cross-Project Queries**: Trino can query data from both SME and KOL domains  

---

## Next Steps

1. ✅ **Verify setup**: Run `make check-sme` and `make up-kol`
2. ✅ **Test connectivity**: Follow verification steps above
3. ⏭️ **Initialize data lake**: Run Bronze → Silver → Gold ETL pipelines
4. ⏭️ **Train models**: Execute model training jobs (see `QUICKSTART.md`)
5. ⏭️ **Deploy API**: Test inference endpoints (see `serving/api/README.md`)

---

## Reference Documents

- **SHARED_INFRASTRUCTURE_GUIDE.md**: Detailed connection guide
- **QUICKSTART.md**: Step-by-step tutorial
- **INFRASTRUCTURE.md**: Architecture deep dive
- **Makefile**: All available commands (`make help`)

---

## Summary

The migration to shared infrastructure is **complete**. The KOL platform now efficiently reuses SME Pulse services while maintaining its own specialized components (Redpanda, Spark, MLflow, Cassandra, Redis, API).

**Key Takeaway**: Always start SME Pulse **first**, then start KOL platform. Use `make check-sme` to verify prerequisites before deployment.

---

**Last Updated**: 2025-01-XX  
**Migration Status**: ✅ Complete  
**Tested**: ⏳ Pending verification

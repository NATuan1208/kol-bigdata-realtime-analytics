# ============================================================================
# SHARED INFRASTRUCTURE SETUP GUIDE
# ============================================================================
# Guide to connect KOL Platform with existing SME Pulse infrastructure
# ============================================================================

## 🎯 Objective

Reuse the following services from SME Pulse:
- MinIO (S3-compatible storage)
- PostgreSQL (metadata DB)
- Trino (query engine)
- Hive Metastore
- dbt
- Airflow
- Metabase (optional)

## 📐 Architecture

```
SME Pulse Project (already running)
├── MinIO (sme-minio:9000, 9001)
├── PostgreSQL (sme-postgres:5432)
├── Trino (sme-trino:8080)
├── Hive Metastore (sme-hive-metastore:9083)
├── Airflow (sme-airflow-webserver:8081)
├── dbt (sme-dbt)
└── Metabase (sme-metabase:3000)
         ↓
    [sme-network]
         ↓
KOL Platform Project (this project)
├── Redpanda (kol-redpanda:19092, 8082)
├── Spark Master/Workers (kol-spark-master:7077, 8084)
├── MLflow (kol-mlflow:5000) → uses sme-postgres & sme-minio
├── Cassandra (kol-cassandra:9042)
├── Redis (kol-redis:6379)
├── Trainer (kol-trainer)
├── API (kol-api:8080)
└── Jupyter (kol-jupyter:8888)
```

## 🔧 Setup Steps

### Step 1: Create Shared Network

Run this command **once** to create a shared network:

```powershell
docker network create sme-network
```

### Step 2: Update SME Pulse docker-compose.yml

In your SME Pulse project, ensure the network section looks like this:

```yaml
networks:
  sme-network:
    name: sme-network
    external: true  # Mark as external so other projects can join
```

And ensure all services use this network:

```yaml
services:
  postgres:
    container_name: sme-postgres
    networks:
      - sme-network
    # ... rest of config
  
  minio:
    container_name: sme-minio
    networks:
      - sme-network
    # ... rest of config
  
  trino:
    container_name: sme-trino
    networks:
      - sme-network
    # ... rest of config
```

### Step 3: Ensure PostgreSQL Creates MLflow Database

In SME Pulse's PostgreSQL initialization script (`sql/init.sql`), add:

```sql
-- Create database for MLflow
CREATE DATABASE IF NOT EXISTS mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO your_postgres_user;
```

### Step 4: Start SME Pulse Infrastructure

```powershell
# In SME Pulse project directory
docker compose up -d
```

Verify services are running:
```powershell
docker ps | findstr sme-
```

### Step 5: Update KOL Platform docker-compose.kol.yml

The KOL platform will now connect to SME Pulse services via the shared network.

Key changes:
- Network: Use `sme-network` (external)
- PostgreSQL host: `sme-postgres`
- MinIO host: `sme-minio`
- Trino host: `sme-trino`

### Step 6: Start KOL Platform

```powershell
# In KOL Platform project directory
cd "d:\SinhVien\UIT_HocChinhKhoa\HK1 2025 - 2026\Bigdata_IE212\DoAn\kol-platform"

# Start KOL services only (they will connect to SME services)
docker compose -f infra/docker-compose.kol.yml up -d
```

## 🌐 Service Access Points

### SME Pulse Services (from SME project)
- MinIO Console: http://localhost:9001
- Trino: http://localhost:8080
- Airflow: http://localhost:8081
- Metabase: http://localhost:3000
- PostgreSQL: localhost:5432

### KOL Platform Services (from this project)
- Redpanda Console: http://localhost:8082
- Spark Master: http://localhost:8084
- MLflow: http://localhost:5000 (uses sme-postgres & sme-minio)
- API: http://localhost:8080/docs (or different port if conflict)
- Jupyter: http://localhost:8888

## 🔍 Verify Connection

### Test from KOL containers to SME services:

```powershell
# Test PostgreSQL connection
docker exec kol-mlflow ping sme-postgres

# Test MinIO connection
docker exec kol-mlflow curl http://sme-minio:9000/minio/health/live

# Test Trino connection
docker exec kol-trainer ping sme-trino
```

## 🚨 Port Conflicts

If there are port conflicts (e.g., both projects expose port 8080):

1. **Change ports in KOL `.env.kol`**:
   ```ini
   API_PORT=8090  # Instead of 8080
   MLFLOW_PORT=5001  # Instead of 5000
   ```

2. **Or use different host ports** in docker-compose.kol.yml:
   ```yaml
   api:
     ports:
       - "8090:8080"  # Host:Container
   ```

## 📝 Environment Variables Mapping

KOL services need these environment variables to connect to SME services:

```ini
# PostgreSQL (from SME Pulse)
POSTGRES_HOST=sme-postgres
POSTGRES_PORT=5432
POSTGRES_USER=<same as SME>
POSTGRES_PASSWORD=<same as SME>

# MinIO (from SME Pulse)
MINIO_ENDPOINT=http://sme-minio:9000
MINIO_ACCESS_KEY=<same as SME>
MINIO_SECRET_KEY=<same as SME>
AWS_ACCESS_KEY_ID=<same as SME>
AWS_SECRET_ACCESS_KEY=<same as SME>
MLFLOW_S3_ENDPOINT_URL=http://sme-minio:9000

# Trino (from SME Pulse)
TRINO_HOST=sme-trino
TRINO_PORT=8080

# Hive Metastore (from SME Pulse)
HIVE_METASTORE_URI=thrift://sme-hive-metastore:9083
```

## 🔄 Workflow

### Daily Development:

1. **Start SME Pulse** (if not already running):
   ```powershell
   cd <sme-pulse-project-path>
   docker compose up -d
   ```

2. **Start KOL Platform**:
   ```powershell
   cd <kol-platform-project-path>
   make up-kol
   ```

3. **Work on KOL features** while using SME infrastructure

4. **Stop KOL only** (keep SME running):
   ```powershell
   make down-kol
   ```

### When to Restart SME Pulse:

Only restart SME Pulse when you need to:
- Update SME Pulse infrastructure
- Add new databases in PostgreSQL
- Modify Trino catalogs
- Update Airflow DAGs

## 🛠️ Troubleshooting

### Issue: KOL services can't reach SME services

**Solution**:
```powershell
# Check if both projects are on the same network
docker network inspect sme-network

# Should show containers from both SME and KOL projects
```

### Issue: MLflow can't connect to PostgreSQL

**Solution**:
1. Check if `mlflow` database exists in SME Pulse PostgreSQL
2. Verify credentials match
3. Check connection:
   ```powershell
   docker exec kol-mlflow psql -h sme-postgres -U <user> -d mlflow
   ```

### Issue: MinIO S3 connection fails

**Solution**:
1. Verify MinIO is accessible:
   ```powershell
   docker exec kol-trainer curl http://sme-minio:9000/minio/health/live
   ```
2. Check credentials in `.env.kol` match SME Pulse credentials

## 💡 Benefits of This Approach

1. ✅ **No duplication**: One MinIO, one Trino, one PostgreSQL for both projects
2. ✅ **Cost-effective**: Less memory/CPU usage
3. ✅ **Data sharing**: Both projects can access same data lake
4. ✅ **Independent deployment**: Can restart KOL without affecting SME
5. ✅ **Clear separation**: SME Pulse = infrastructure, KOL = application layer

## 🔐 Security Notes

For production:
1. Use Docker secrets instead of environment variables
2. Enable authentication on all services
3. Use TLS for inter-service communication
4. Implement network policies

---

**Next**: Update `docker-compose.kol.yml` with these changes

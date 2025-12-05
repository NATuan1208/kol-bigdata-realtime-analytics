# 🔍 Spark Infrastructure Test Report (2025-11-17)

## Executive Summary

**Current Status:** ⚠️ **PARTIALLY READY**
- ✅ Spark cluster running (Master + 2 Workers)
- ✅ Hadoop client libraries present
- ❌ **MISSING: Iceberg libraries** (iceberg-spark-runtime)
- ❌ **MISSING: S3A AWS connector** (hadoop-aws)

**Action Required:** Build and deploy custom Spark image with missing JARs

---

## Test Results

### 1. Spark Image Analysis
```
Spark Version: 3.5.0 (apache/spark:3.5.0 official image)
Total JARs in image: 252
```

**Present JARs:**
- ✅ hadoop-client-api-3.3.4
- ✅ hadoop-client-runtime-3.3.4
- ✅ hadoop-yarn-server-web-proxy-3.3.4
- ✅ parquet-hadoop-1.13.1
- ✅ spark-core, spark-sql, spark-streaming
- ✅ All standard Spark + Hadoop + Arrow libraries

**Missing JARs:**
- ❌ `hadoop-aws-3.3.4.jar` (S3A connector for MinIO)
- ❌ `aws-java-sdk-bundle.jar` (AWS SDK dependency)
- ❌ `iceberg-spark-runtime-3.5_2.12.jar` (Iceberg Spark integration)

### 2. Connectivity Status

| Component | Status | Note |
|-----------|--------|------|
| Spark Master | ✅ Running | Port 7077 internal, 8084 external |
| Spark Workers | ✅ 2x Running | infra-spark-worker-1/2 |
| Spark History | ✅ Running | Port 18080 external |
| Hive Metastore | ✅ Reachable | thrift://sme-hive-metastore:9083 |
| MinIO | ✅ Reachable | http://sme-minio:9000 (internal) |
| Trino | ✅ Reachable | http://sme-trino:8080 (internal), :8081 (external) |

### 3. What CAN'T Work Yet

Without Iceberg + S3A JARs:

```bash
# ❌ This will FAIL (no Iceberg runtime)
spark.sql("CREATE TABLE kol_lake.kol_bronze.events AS SELECT ...")

# ❌ This will FAIL (no S3A)
spark.read.parquet("s3a://kol-platform/bronze/events/")

# ❌ This will FAIL (no hadoop-aws)
df.write.mode("overwrite").format("parquet").save("s3a://kol-platform/silver/...")
```

### 4. What WILL Work

```bash
# ✅ Reading from local/distributed Spark storage
df = spark.read.parquet("/opt/spark/data/")

# ✅ Writing to Spark warehouse
df.write.mode("overwrite").parquet("/opt/spark/warehouse/...")

# ✅ Querying Hive tables (if created via Trino)
spark.sql("SELECT * FROM default.some_table")

# ✅ Basic Spark operations
spark.sparkContext.parallelize([1,2,3,4]).toDF().show()
```

---

## Solution: Add Missing Libraries

### Option A: Download JARs Manually (Simple)

```bash
# 1. Download JARs to local machine
wget https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.4.0/iceberg-spark-runtime-3.5_2.12-1.4.0.jar
wget https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar
wget https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.11.1034/aws-java-sdk-bundle-1.11.1034.jar

# 2. Copy into Spark container
docker cp iceberg-spark-runtime-3.5_2.12-1.4.0.jar kol-spark-master:/opt/spark/jars/
docker cp hadoop-aws-3.3.4.jar kol-spark-master:/opt/spark/jars/
docker cp aws-java-sdk-bundle-1.11.1034.jar kol-spark-master:/opt/spark/jars/

# 3. Restart Spark services
docker compose -f infra/docker-compose.kol.yml restart spark-master spark-worker
```

**Pros:** Quick, no image rebuild
**Cons:** Manual for each container, lost on container restart

### Option B: Build Custom Image (Recommended)

```bash
# 1. Run build script
bash infra/scripts/setup-spark-iceberg.sh

# This will:
#  - Build kol-spark-with-iceberg:latest image
#  - Pre-download all required JARs
#  - Include them in the image

# 2. Update docker-compose.kol.yml to use custom image
# Change all: image: apache/spark:3.5.0
# To: image: kol-spark-with-iceberg:latest

# 3. Restart Spark services
docker compose -f infra/docker-compose.kol.yml up -d --force-recreate spark-master spark-worker spark-history spark-streaming
```

**Pros:** Persistent, all containers get libs automatically
**Cons:** Larger image, takes time to build (~3-5 min)

---

## Implementation Steps

### Step 1: Build Custom Spark Image

**Already prepared:** `infra/dockerfiles/Dockerfile.spark`

```bash
docker build -f infra/dockerfiles/Dockerfile.spark \
  -t kol-spark-with-iceberg:latest \
  e:\Project\kol-platform
```

Expected output:
```
Successfully built kol-spark-with-iceberg:latest
```

### Step 2: Update docker-compose.kol.yml

Replace ALL Spark image references:

**Before:**
```yaml
spark-master:
  image: apache/spark:3.5.0

spark-worker:
  image: apache/spark:3.5.0

spark-streaming:
  image: apache/spark:3.5.0

spark-history:
  image: apache/spark:3.5.0
```

**After:**
```yaml
spark-master:
  image: kol-spark-with-iceberg:latest

spark-worker:
  image: kol-spark-with-iceberg:latest

spark-streaming:
  image: kol-spark-with-iceberg:latest

spark-history:
  image: kol-spark-with-iceberg:latest
```

### Step 3: Restart Spark Services

```bash
docker compose -f infra/docker-compose.kol.yml up -d --force-recreate \
  spark-master spark-worker spark-history spark-streaming
```

Wait for all to be healthy:
```bash
docker ps --filter "name=spark-" --format "table {{.Names}}\t{{.Status}}"
```

### Step 4: Verify Libraries Loaded

```bash
# Check Iceberg JAR in master
docker exec kol-spark-master ls /opt/spark/jars/iceberg*.jar

# Output should show:
# /opt/spark/jars/iceberg-spark-runtime-3.5_2.12-1.4.0.jar

# Check S3A JAR in master
docker exec kol-spark-master ls /opt/spark/jars/hadoop-aws*.jar

# Output should show:
# /opt/spark/jars/hadoop-aws-3.3.4.jar
```

---

## Size Impact

| Image | Size | Delta |
|-------|------|-------|
| apache/spark:3.5.0 | ~1.0 GB | - |
| kol-spark-with-iceberg:latest | ~1.2 GB | +200 MB |

Total for 4 containers (master + 2 workers + history):
- Before: 4.0 GB (shared layer)
- After: ~1.2 GB (shared layer, only stored once)

**Net impact:** +200 MB disk (one-time)

---

## What Happens After

Once custom image is deployed, you'll be able to:

✅ Create Iceberg tables
```python
spark.sql("""
    CREATE TABLE kol_lake.kol_bronze.events (
        event_id STRING,
        kol_id STRING,
        created_at TIMESTAMP
    )
    USING iceberg
""")
```

✅ Read from MinIO S3A
```python
df = spark.read.parquet("s3a://kol-platform/bronze/events/")
```

✅ Write to MinIO S3A with Iceberg
```python
df.write \
  .format("iceberg") \
  .mode("overwrite") \
  .save("s3a://kol-platform/silver/events/")
```

✅ Run spark-submit jobs with Iceberg
```bash
spark-submit \
  --master spark://kol-spark-master:7077 \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.kol_lake=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.kol_lake.type=hive \
  --conf spark.sql.catalog.kol_lake.uri=thrift://sme-hive-metastore:9083 \
  --conf spark.hadoop.fs.s3a.endpoint=http://sme-minio:9000 \
  --conf spark.hadoop.fs.s3a.access.key=minio \
  --conf spark.hadoop.fs.s3a.secret.key=minio123 \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  /path/to/batch/etl/load_bronze_data.py
```

---

## Recommendation

**👉 Use Option B (Custom Image)** because:

1. ✅ All Spark services automatically get libraries
2. ✅ Libraries persist across container restarts
3. ✅ No manual copying for each container
4. ✅ Clean, reproducible build
5. ✅ Only +200 MB image size increase
6. ✅ Standard Docker best practice

---

## Files Prepared

1. ✅ `infra/dockerfiles/Dockerfile.spark` - Custom Spark image definition
2. ✅ `infra/scripts/setup-spark-iceberg.sh` - Build automation script
3. ✅ This report file

---

## Next Steps for You

1. **Review this report** - Confirm you need Iceberg + S3A
2. **Build custom image:**
   ```bash
   docker build -f infra/dockerfiles/Dockerfile.spark \
     -t kol-spark-with-iceberg:latest \
     .
   ```
3. **Update docker-compose.kol.yml** - Replace image references
4. **Restart Spark services:**
   ```bash
   docker compose -f infra/docker-compose.kol.yml up -d --force-recreate spark-master spark-worker spark-history spark-streaming
   ```
5. **Verify JARs loaded:**
   ```bash
   docker exec kol-spark-master ls /opt/spark/jars/iceberg*.jar
   docker exec kol-spark-master ls /opt/spark/jars/hadoop-aws*.jar
   ```

Then you're ready for Phase 1 data ingestion! 🚀

---

**Report Generated:** 2025-11-17
**Spark Version:** 3.5.0
**Iceberg Version:** 1.4.0
**Hadoop Version:** 3.3.4

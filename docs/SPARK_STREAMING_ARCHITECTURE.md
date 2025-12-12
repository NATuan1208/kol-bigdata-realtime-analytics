# 🔥 Spark Streaming Architecture - Design Decision Document

> **Author:** Principal Data Solutions Architect  
> **Version:** 1.0  
> **Last Updated:** 2024-12-14

---

## 📋 Executive Summary

This document explains the **intentional design decision** behind running Spark Streaming containers with `tail -f /dev/null` command, and provides guidance on how to properly operate streaming jobs in production.

---

## 🏗️ Architecture Overview

### Lambda Architecture Pattern

```
                    ┌─────────────────────────────────────────────┐
                    │           KOL Analytics Platform            │
                    └─────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────▼───────┐   ┌───────▼───────┐   ┌───────▼───────┐
            │   Hot Path    │   │   Cold Path   │   │   Serving     │
            │  (Real-time)  │   │   (Batch)     │   │   Layer       │
            └───────────────┘   └───────────────┘   └───────────────┘
                    │                   │                   │
            Kafka → Spark        MinIO → Spark        Redis + Trino
            Streaming            Batch ETL            + FastAPI
                    │                   │                   │
                    ▼                   ▼                   ▼
            Redis Trending      Gold Tables         Dashboard/API
            Scores (seconds)    (daily/hourly)      Response (<50ms)
```

---

## 🤔 Why `tail -f /dev/null`?

### The Design Decision

In `docker-compose.kol.yml`, you'll notice:

```yaml
kol-spark-streaming:
  container_name: kol-spark-streaming
  build:
    context: ./streaming
    dockerfile: Dockerfile.streaming
  command: ["tail", "-f", "/dev/null"]  # ← Intentional!
  volumes:
    - ./streaming/spark_jobs:/opt/spark-jobs:ro
```

### Reasons for This Approach

| # | Reason | Explanation |
|---|--------|-------------|
| 1 | **Manual Job Control** | Streaming jobs should be submitted manually, not auto-started |
| 2 | **Development Flexibility** | Easy to modify and test different streaming configurations |
| 3 | **Resource Management** | Prevents unnecessary resource consumption when not actively developing |
| 4 | **Container Persistence** | Keeps container alive for `docker exec` access |
| 5 | **Hot Reload** | Volume mount allows code changes without container restart |

### Alternative Approaches

| Approach | Pros | Cons |
|----------|------|------|
| Auto-start job | Simple startup | Hard to debug, consumes resources |
| Kubernetes | Production-ready | Complex for development |
| `tail -f /dev/null` | Flexible, debuggable | Requires manual start |

---

## 🚀 Running Spark Streaming Jobs

### Method 1: Interactive Job Submission (Recommended for Dev)

```bash
# 1. Connect to the container
docker exec -it kol-spark-streaming bash

# 2. Submit the streaming job
spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
  --conf spark.executor.memory=1g \
  --conf spark.driver.memory=1g \
  /opt/spark-jobs/trending_stream.py
```

### Method 2: One-liner from Host (Production-ready)

```bash
docker exec kol-spark-streaming spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
  --conf spark.executor.memory=2g \
  --conf spark.driver.memory=1g \
  --conf spark.streaming.kafka.maxRatePerPartition=1000 \
  /opt/spark-jobs/trending_stream.py
```

### Method 3: Using Makefile (Simplified)

Add to Makefile:
```makefile
streaming-start:
	docker exec kol-spark-streaming spark-submit \
		--master spark://spark-master:7077 \
		--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
		/opt/spark-jobs/trending_stream.py

streaming-status:
	docker exec kol-spark-streaming ps aux | grep spark-submit
```

Then run: `make streaming-start`

---

## ⚙️ Spark Streaming Configuration

### Key Settings for Production

```python
# In trending_stream.py

spark = SparkSession.builder \
    .appName("KOL-Trending-Stream") \
    .master("spark://spark-master:7077") \
    .config("spark.sql.streaming.checkpointLocation", "/opt/spark-jobs/checkpoint") \
    .config("spark.sql.streaming.stateStore.providerClass", 
            "org.apache.spark.sql.execution.streaming.state.HDFSBackedStateStoreProvider") \
    .config("spark.streaming.kafka.maxRatePerPartition", "1000") \
    .config("spark.executor.memory", "2g") \
    .config("spark.driver.memory", "1g") \
    .getOrCreate()
```

### Kafka Consumer Settings

```python
# Read from Kafka
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "redpanda:9092") \
    .option("subscribe", "kol-profiles-raw") \
    .option("startingOffsets", "latest") \
    .option("failOnDataLoss", "false") \
    .option("kafka.group.id", "kol-streaming-consumer") \
    .load()
```

---

## 📊 Monitoring Streaming Jobs

### Check Job Status

```bash
# View running processes
docker exec kol-spark-streaming ps aux | grep spark

# Check Spark UI (if exposed)
# http://localhost:4040

# View logs
docker logs -f kol-spark-streaming

# Check checkpoint directory
docker exec kol-spark-streaming ls -la /opt/spark-jobs/checkpoint/
```

### Health Checks

```bash
# Verify Redis is receiving updates
redis-cli -h localhost -p 16379 ZRANGE ranking:tiktok:trending 0 -1 WITHSCORES

# Check last update time
redis-cli -h localhost -p 16379 GET streaming:last_update
```

---

## 🔄 Graceful Restart Procedure

### Stopping a Streaming Job

```bash
# Find the job PID
docker exec kol-spark-streaming pgrep -f spark-submit

# Send SIGTERM for graceful shutdown
docker exec kol-spark-streaming kill -15 <PID>

# Or force stop
docker exec kol-spark-streaming kill -9 <PID>
```

### Full Restart

```bash
# Stop container
docker-compose stop kol-spark-streaming

# Clear checkpoints (if needed)
docker-compose run --rm kol-spark-streaming rm -rf /opt/spark-jobs/checkpoint/*

# Restart container
docker-compose up -d kol-spark-streaming

# Submit job
docker exec kol-spark-streaming spark-submit ...
```

---

## 🏭 Production Deployment Recommendations

### 1. Use a Process Supervisor

For production, replace `tail -f /dev/null` with a supervisor:

```dockerfile
# Dockerfile.streaming.production
FROM bitnami/spark:3.5.1

RUN pip install supervisor

COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY streaming/spark_jobs /opt/spark-jobs

CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

### 2. Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spark-streaming-job
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kol-streaming
  template:
    spec:
      containers:
      - name: spark-streaming
        image: kol-spark-streaming:latest
        command: ["spark-submit"]
        args:
          - "--master"
          - "spark://spark-master:7077"
          - "/opt/spark-jobs/trending_stream.py"
        resources:
          limits:
            memory: "4Gi"
            cpu: "2"
```

### 3. Auto-restart on Failure

```yaml
# docker-compose.kol.yml (production)
kol-spark-streaming:
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 4G
      reservations:
        memory: 2G
```

---

## 📈 Scaling Considerations

| Scale Level | Configuration | Notes |
|-------------|---------------|-------|
| Dev/Test | 1 executor, 1g memory | Single container |
| Small | 2 executors, 2g each | Up to 100K events/sec |
| Medium | 4 executors, 4g each | Up to 500K events/sec |
| Large | 8+ executors, 8g each | 1M+ events/sec |

---

## 🔧 Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Job not starting | Missing packages | Add `--packages` flag |
| Kafka connection refused | Wrong broker address | Check `kafka.bootstrap.servers` |
| Out of memory | Too much state | Increase executor memory |
| No data in Redis | Kafka empty | Check topic has messages |
| Checkpoint errors | Corrupted state | Clear checkpoint directory |

### Debug Commands

```bash
# Check Kafka connectivity
docker exec kol-spark-streaming \
  kafka-console-consumer.sh \
  --bootstrap-server redpanda:9092 \
  --topic kol-profiles-raw \
  --from-beginning \
  --max-messages 5

# Test Redis connectivity
docker exec kol-spark-streaming \
  redis-cli -h redis -p 6379 PING
```

---

## 📚 Related Documentation

- [DATA_PIPELINE.md](./DATA_PIPELINE.md) - Overall data flow
- [E2E_TEST_REPORT.md](./E2E_TEST_REPORT_20251213.md) - Testing results
- [ML_PIPELINE.md](./ML_PIPELINE.md) - ML model integration

---

## ✅ Checklist for Production Deployment

- [ ] Configure proper checkpoint location (persistent volume)
- [ ] Set appropriate Kafka consumer group ID
- [ ] Configure memory limits based on workload
- [ ] Set up monitoring alerts
- [ ] Enable auto-restart on failure
- [ ] Configure log aggregation
- [ ] Test graceful shutdown procedure
- [ ] Document rollback procedure
- [ ] Set up backup for checkpoint data

---

*This design document reflects the intentional architecture choices made for flexibility during development while providing a clear path to production deployment.*

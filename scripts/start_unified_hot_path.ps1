# PowerShell script to start Unified Hot Path Streaming
# =======================================================
# This script starts the complete scoring pipeline:
# - Trust Score (from profiles)
# - Trending Score (from videos)
# - Success Score (from products)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  UNIFIED HOT PATH - Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Configuration
$SPARK_MASTER = "spark://spark-master:7077"
$KAFKA_PACKAGES = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1"
$SPARK_CONTAINER = "kol-spark-master"
$JOB_PATH = "/opt/spark-jobs/unified_hot_path.py"

# Check if containers are running
Write-Host "`n[1/4] Checking containers..." -ForegroundColor Yellow

$containers = @("kol-spark-master", "redpanda", "kol-redis")
foreach ($container in $containers) {
    $status = docker inspect -f '{{.State.Running}}' $container 2>$null
    if ($status -eq "true") {
        Write-Host "  ✅ $container is running" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $container is NOT running!" -ForegroundColor Red
        Write-Host "     Run: docker-compose up -d" -ForegroundColor Yellow
        exit 1
    }
}

# Copy job files to Spark container
Write-Host "`n[2/4] Copying job files to Spark container..." -ForegroundColor Yellow

$jobFiles = @(
    "streaming/spark_jobs/unified_hot_path.py",
    "streaming/spark_jobs/multi_topic_hot_path.py",
    "streaming/spark_jobs/hot_path_scoring.py"
)

foreach ($file in $jobFiles) {
    if (Test-Path $file) {
        docker cp $file "${SPARK_CONTAINER}:/opt/spark-jobs/"
        Write-Host "  ✅ Copied $file" -ForegroundColor Green
    }
}

# Copy model artifacts if exist
Write-Host "`n[3/4] Copying model artifacts..." -ForegroundColor Yellow

$modelFiles = @(
    "models/artifacts/success/success_lgbm_model.pkl",
    "models/artifacts/success/success_scaler.pkl"
)

# Create models directory in container
docker exec $SPARK_CONTAINER mkdir -p /opt/spark-jobs/models 2>$null

foreach ($model in $modelFiles) {
    if (Test-Path $model) {
        docker cp $model "${SPARK_CONTAINER}:/opt/spark-jobs/models/"
        Write-Host "  ✅ Copied $model" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Model not found: $model (will use rule-based fallback)" -ForegroundColor Yellow
    }
}

# Start the streaming job
Write-Host "`n[4/4] Starting Spark Streaming job..." -ForegroundColor Yellow
Write-Host "----------------------------------------"

# Choose which job to run
$jobChoice = Read-Host "Select job: [1] unified_hot_path (default) [2] multi_topic_hot_path [3] hot_path_scoring"

switch ($jobChoice) {
    "2" {
        $JOB_PATH = "/opt/spark-jobs/multi_topic_hot_path.py"
        $JOB_NAME = "multi_topic_hot_path"
    }
    "3" {
        $JOB_PATH = "/opt/spark-jobs/hot_path_scoring.py"
        $JOB_NAME = "hot_path_scoring"
    }
    default {
        $JOB_PATH = "/opt/spark-jobs/unified_hot_path.py"
        $JOB_NAME = "unified_hot_path"
    }
}

Write-Host "`n🚀 Starting: $JOB_NAME" -ForegroundColor Cyan
Write-Host "   Master: $SPARK_MASTER"
Write-Host "   Job: $JOB_PATH"
Write-Host "`nPress Ctrl+C to stop the job.`n" -ForegroundColor Yellow

# Run spark-submit
docker exec -it $SPARK_CONTAINER spark-submit `
    --master $SPARK_MASTER `
    --packages $KAFKA_PACKAGES `
    --conf "spark.executor.memory=1g" `
    --conf "spark.driver.memory=1g" `
    --conf "spark.sql.shuffle.partitions=4" `
    --conf "spark.streaming.stopGracefullyOnShutdown=true" `
    $JOB_PATH

Write-Host "`n✅ Job completed or stopped." -ForegroundColor Green

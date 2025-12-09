<#
.SYNOPSIS
    Start Full KOL Platform - Infrastructure + Scrapers + Streaming

.DESCRIPTION
    Khởi động toàn bộ hệ thống KOL Platform:
    1. Check Docker containers (Kafka, Redis, Spark)
    2. Start Spark Streaming job (trending calculation)
    3. Start parallel scrapers (discovery + workers + refresh)
    
    Sau khi chạy, hệ thống sẽ:
    - Tự động discovery KOL mới (CHỈ PUSH TOP N LÊN KAFKA)
    - Scrape video stats, comments, products
    - Tính trending score real-time
    - Re-fresh tracked KOLs mỗi 5 phút để tính velocity
    
    ⚠️ Limit Control:
    Discovery tìm 20-30 KOLs nhưng chỉ push TOP N (default 20) lên Kafka
    → Workers chỉ scrape TOP N KOLs → Kiểm soát volume và thời gian

.EXAMPLE
    .\scripts\start_full_platform.ps1
    
.EXAMPLE
    # Chỉ chạy discovery + video stats (không comments/products)
    .\scripts\start_full_platform.ps1 -NoComments -NoProducts
#>

param(
    [switch]$NoComments,
    [switch]$NoProducts,
    [switch]$NoRefresh,
    [switch]$SkipInfraCheck,
    [int]$MaxKols = 20,
    [int]$MaxVideos = 20,
    [int]$DiscoveryInterval = 7200,   # 2 tiếng discovery 1 lần
    [int]$RefreshInterval = 300,      # 5 phút refresh 1 lần  
    [int]$WorkerDelay = 240           # Workers đợi 4 phút
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  KOL PLATFORM - Full Stack Startup" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# ==================== STEP 1: Check Infrastructure ====================
if (-not $SkipInfraCheck) {
    Write-Host "[1/3] Checking infrastructure..." -ForegroundColor Yellow
    
    # Check Redis
    $redisCheck = docker exec kol-redis redis-cli PING 2>$null
    if ($redisCheck -ne "PONG") {
        Write-Host "  ❌ Redis not running!" -ForegroundColor Red
        Write-Host "  Run: cd infra && docker-compose up -d" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✅ Redis OK" -ForegroundColor Green
    
    # Check Kafka
    $kafkaCheck = docker exec kol-redpanda rpk cluster health 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Kafka (Redpanda) not running!" -ForegroundColor Red
        Write-Host "  Run: cd infra && docker-compose up -d" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✅ Kafka OK" -ForegroundColor Green
    
    # Check Spark
    $sparkCheck = docker exec kol-spark-master curl -s http://localhost:8080/json/ 2>$null | Select-String "status"
    if (-not $sparkCheck) {
        Write-Host "  ❌ Spark not running!" -ForegroundColor Red
        Write-Host "  Run: cd infra && docker-compose up -d" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✅ Spark OK" -ForegroundColor Green
    Write-Host ""
}

# ==================== STEP 2: Start Spark Streaming ====================
Write-Host "[2/3] Starting Spark Streaming job..." -ForegroundColor Yellow

# Check if job already running
$sparkJobs = docker exec kol-spark-master curl -s http://localhost:8080/json/ 2>$null | Select-String "KOL-Trending-STREAM"
if ($sparkJobs) {
    Write-Host "  ✅ Spark Streaming already running" -ForegroundColor Green
} else {
    # Install redis in Spark container if needed
    Write-Host "  Installing redis package in Spark..." -ForegroundColor Gray
    docker exec -u root kol-spark-master pip install redis -q 2>$null
    
    # Clear old checkpoints
    Write-Host "  Clearing old checkpoints..." -ForegroundColor Gray
    docker exec kol-spark-master rm -rf /tmp/checkpoints/kol-trending 2>$null
    
    # Start Spark Streaming job
    Write-Host "  Starting Spark Streaming job..." -ForegroundColor Gray
    docker exec -d kol-spark-master /opt/spark/bin/spark-submit `
        --master spark://spark-master:7077 `
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 `
        /opt/spark-jobs/kafka_trending_stream.py
    
    Start-Sleep -Seconds 5
    
    # Verify
    $sparkJobs = docker exec kol-spark-master curl -s http://localhost:8080/json/ 2>$null | Select-String "KOL-Trending-STREAM"
    if ($sparkJobs) {
        Write-Host "  ✅ Spark Streaming started" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ Spark Streaming may take a moment to start" -ForegroundColor Yellow
    }
}
Write-Host ""

# ==================== STEP 3: Start Scrapers ====================
Write-Host "[3/3] Starting parallel scrapers..." -ForegroundColor Yellow

$scraperCmd = "$ProjectRoot\scripts\start_parallel_scrapers.ps1 -MaxKols $MaxKols -MaxVideos $MaxVideos -DiscoveryInterval $DiscoveryInterval -RefreshInterval $RefreshInterval -WorkerDelay $WorkerDelay"
if ($NoComments) { $scraperCmd += " -NoComments" }
if ($NoProducts) { $scraperCmd += " -NoProducts" }
if ($NoRefresh) { $scraperCmd += " -NoRefresh" }

Invoke-Expression $scraperCmd

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Green
Write-Host "  KOL Platform Started Successfully!" -ForegroundColor Green
Write-Host "=" * 70 -ForegroundColor Green
Write-Host ""
Write-Host "  Monitoring:" -ForegroundColor Cyan
Write-Host "    Spark UI:       http://localhost:8084"
Write-Host "    Kafka Console:  http://localhost:8080"
Write-Host "    Redis:          docker exec kol-redis redis-cli KEYS 'streaming_scores:*'"
Write-Host ""
Write-Host "  Check trending scores:" -ForegroundColor Cyan
Write-Host "    docker exec kol-redis redis-cli HGETALL 'streaming_scores:<username>'"
Write-Host ""

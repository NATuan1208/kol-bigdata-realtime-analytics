<#
.SYNOPSIS
    Start KOL Scraper Pipeline - 4 Workers Song Song + Metrics Refresh

.DESCRIPTION
    Flow mới (tối ưu thời gian + trending velocity):
    1. Scraper discovery username → push TOP N lên kol.discovery.raw (GIỚI HẠN!)
    2. Cả 3 workers cùng lắng nghe discovery.raw:
       - Video Stats Worker: lấy profile + video stats
       - Comment Extractor: lấy comments từ videos
       - Product Extractor: lấy products từ videos
    3. Metrics Refresh: Re-push tracked KOLs mỗi 5 phút để tính velocity
    
    Mỗi worker dùng Chrome profile riêng (trong data/chrome_profiles/).
    
    Trending Flow:
    - Discovery tìm KOL mới → VideoStatsWorker scrape → Kafka → Spark → Redis
    - Metrics Refresh re-push KOL cũ → VideoStatsWorker scrape lại → velocity!
    
    ⚠️ QUAN TRỌNG:
    -MaxKols 5 = Discovery có thể tìm 20-30 KOLs nhưng CHỈ PUSH TOP 5 LÊN KAFKA!
    → Workers chỉ nhận 5 messages → Chỉ scrape 5 KOLs → Kiểm soát volume

.EXAMPLE
    .\scripts\start_parallel_scrapers.ps1
    
.EXAMPLE
    # Chỉ chạy 2 workers (không lấy comments)
    .\scripts\start_parallel_scrapers.ps1 -NoComments
    
.EXAMPLE
    # Không chạy Metrics Refresh (chỉ discovery, không tracking)
    .\scripts\start_parallel_scrapers.ps1 -NoRefresh
#>

param(
    [switch]$NoComments,
    [switch]$NoProducts,
    [switch]$NoVideoStats,
    [switch]$NoRefresh,
    [switch]$DryRun,
    [int]$MaxKols = 20,
    [int]$MaxVideos = 20,
    [int]$DiscoveryInterval = 7200,   # 2 tiếng chạy discovery 1 lần
    [int]$RefreshInterval = 300,      # 5 phút refresh 1 lần
    [int]$WorkerDelay = 240           # Workers đợi 4 phút cho discovery
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# Check venv exists
if (-not (Test-Path $VenvPython)) {
    Write-Error "Python venv not found at: $VenvPython"
    exit 1
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  KOL SCRAPER PIPELINE - Parallel Workers + Trending" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Yellow
Write-Host "    Max KOLs per round:   $MaxKols"
Write-Host "    Max videos per KOL:   $MaxVideos"
Write-Host "    Discovery Interval:   $DiscoveryInterval seconds ($([math]::Round($DiscoveryInterval/3600, 1)) hours)"
Write-Host "    Refresh Interval:     $RefreshInterval seconds ($([math]::Round($RefreshInterval/60, 1)) min)"
Write-Host "    Worker Start Delay:   $WorkerDelay seconds"
Write-Host "    Video Stats Worker:   $(if ($NoVideoStats) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Comment Extractor:    $(if ($NoComments) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Product Extractor:    $(if ($NoProducts) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Metrics Refresh:      $(if ($NoRefresh) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Dry Run: $DryRun"
Write-Host ""
Write-Host "  Chrome Profiles (auto-created in data/chrome_profiles/):" -ForegroundColor Yellow
Write-Host "    Discovery:    discovery"
Write-Host "    Video Stats:  video_stats_worker"
Write-Host "    Comments:     comment_extractor"
Write-Host "    Products:     product_extractor"
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Function to start a worker in new terminal
function Start-Worker {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Color
    )
    
    $title = "KOL - $Name"
    
    # Build PowerShell command
    $psCommand = @"
`$Host.UI.RawUI.WindowTitle = '$title'
Set-Location '$ProjectRoot'
& '$VenvPython' $Command
Read-Host 'Press Enter to close...'
"@
    
    Write-Host "  Starting $Name..." -ForegroundColor $Color
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $psCommand
    Start-Sleep -Seconds 2
}

# ==================== RESET CONSUMER GROUPS ====================

Write-Host "Resetting consumer groups to LATEST..." -ForegroundColor Yellow
Write-Host ""

# Reset tất cả consumer groups về end (chỉ đọc messages mới)
$consumerGroups = @("kol-video-stats-v3", "kol-comment-extractor-v3", "kol-product-extractor-v3")

foreach ($group in $consumerGroups) {
    try {
        $result = docker exec kol-redpanda rpk group seek $group --to end 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Reset $group" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  $group not found (will be created on first consume)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  ⚠️  Could not reset $group (may not exist yet)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# ==================== START WORKERS ====================

Write-Host "Starting workers..." -ForegroundColor Green
Write-Host ""

# 1. Discovery Scraper (produces to kol.discovery.raw)
# Chạy mỗi 2-6 tiếng để tìm KOL mới (không cần chạy thường xuyên)
$discoveryArgs = "-m ingestion.sources.kol_scraper daemon --discovery-only --max-kols-per-round $MaxKols --interval $DiscoveryInterval"
if ($DryRun) { $discoveryArgs += " --dry-run" }
Start-Worker -Name "Discovery Daemon" -Command $discoveryArgs -Color "Green"

# 2. Video Stats Worker (consumes discovery.raw -> produces videos.raw + profiles.raw)
# Delay để đợi Discovery push messages trước
if (-not $NoVideoStats) {
    Write-Host "  ⏳ Video Stats Worker sẽ start sau ${WorkerDelay}s (đợi Discovery)..." -ForegroundColor Gray
    $videoArgs = "-m ingestion.consumers.video_stats_worker --max-videos $MaxVideos --start-delay $WorkerDelay"
    if ($DryRun) { $videoArgs += " --dry-run" }
    Start-Worker -Name "Video Stats Worker" -Command $videoArgs -Color "Cyan"
}

# 3. Comment Extractor (consumes discovery.raw -> produces comments.raw)
# Delay để đợi Discovery push messages trước
if (-not $NoComments) {
    Write-Host "  ⏳ Comment Extractor sẽ start sau ${WorkerDelay}s (đợi Discovery)..." -ForegroundColor Gray
    $commentArgs = "-m ingestion.consumers.comment_extractor --max-videos $MaxVideos --start-delay $WorkerDelay"
    if ($DryRun) { $commentArgs += " --dry-run" }
    Start-Worker -Name "Comment Extractor" -Command $commentArgs -Color "Yellow"
}

# 4. Product Extractor (consumes discovery.raw -> produces products.raw)
# Delay để đợi Discovery push messages trước
if (-not $NoProducts) {
    Write-Host "  ⏳ Product Extractor sẽ start sau ${WorkerDelay}s (đợi Discovery)..." -ForegroundColor Gray
    $productArgs = "-m ingestion.consumers.product_extractor --max-videos $MaxVideos --start-delay $WorkerDelay"
    if ($DryRun) { $productArgs += " --dry-run" }
    Start-Worker -Name "Product Extractor" -Command $productArgs -Color "Magenta"
}

# 5. Metrics Refresh (re-push tracked KOLs for velocity calculation)
if (-not $NoRefresh) {
    $refreshArgs = "-m ingestion.sources.metrics_refresh --interval $RefreshInterval"
    Start-Worker -Name "Metrics Refresh" -Command $refreshArgs -Color "Blue"
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "  All workers started!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "  Flow:" -ForegroundColor Yellow
Write-Host "    Discovery -> discovery.raw <-- Metrics Refresh (re-push)"
Write-Host "                  |                     ^"
Write-Host "         +--------+--------+            |"
Write-Host "         v        v        v            |"
Write-Host "      Video    Comment  Product         |"
Write-Host "      Worker   Extract  Extract         |"
Write-Host "         |        |        |            |"
Write-Host "         v        v        v            |"
Write-Host "    videos.raw comments  products       |"
Write-Host "         |                              |"
Write-Host "         v                              |"
Write-Host "    Spark Streaming                     |"
Write-Host "         |                              |"
Write-Host "         v                              |"
Write-Host "       Redis ---------------------->----+"
Write-Host "    (trending scores)"
Write-Host ""
Write-Host "  Trending Velocity:" -ForegroundColor Cyan
Write-Host "    - Metrics Refresh re-push KOLs moi $RefreshInterval giay"
Write-Host "    - VideoStatsWorker scrape lai -> tinh velocity"
Write-Host "    - Spark Streaming tinh score = delta metrics"
Write-Host ""
Write-Host "  Tips:" -ForegroundColor Yellow
Write-Host "    - Press Ctrl+C in each terminal to stop gracefully"
Write-Host "    - Check logs in data/logs/ folder"
Write-Host "    - View Kafka: http://localhost:8080 (Redpanda Console)"
Write-Host "    - View Spark: http://localhost:8084 (Spark UI)"
Write-Host "    - Check Redis: docker exec kol-redis redis-cli KEYS 'streaming_scores:*'"
Write-Host ""

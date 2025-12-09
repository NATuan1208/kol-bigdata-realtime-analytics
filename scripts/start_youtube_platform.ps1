<#
.SYNOPSIS
    Start YouTube KOL Platform - Discovery + Workers

.DESCRIPTION
    Flow YouTube (Hybrid: Selenium + API):
    1. YouTube Discovery (Selenium) → tìm trending shorts channels
    2. YouTube Stats Worker (API) → lấy channel + videos stats
    3. YouTube Comments Worker (API) → lấy comments
    4. Metrics Refresh → re-push tracked channels
    
    REUSE TikTok infrastructure:
    - Kafka topics: kol.discovery.raw, kol.videos.raw, kol.profiles.raw, kol.comments.raw
    - Spark Streaming: kafka_trending_stream.py (đã support platform field)
    - Redis: streaming_scores:{username}
    - Dashboard: serving/dashboard/app.py (filter by platform)

.EXAMPLE
    .\scripts\start_youtube_platform.ps1
    
.EXAMPLE
    .\scripts\start_youtube_platform.ps1 -MaxChannels 5 -MaxVideos 30 -NoComments
#>

param(
    [switch]$NoComments,
    [switch]$NoRefresh,
    [int]$MaxChannels = 10,
    [int]$MaxVideos = 50,
    [int]$DiscoveryInterval = 7200,   # 2 hours
    [int]$RefreshInterval = 300,      # 5 minutes
    [int]$WorkerDelay = 240           # 4 minutes
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# Check venv
if (-not (Test-Path $VenvPython)) {
    Write-Error "Python venv not found at: $VenvPython"
    exit 1
}

# Check YouTube API key
if (-not $env:YOUTUBE_API_KEY) {
    Write-Error "YOUTUBE_API_KEY environment variable not set!"
    Write-Host "  Set it: `$env:YOUTUBE_API_KEY='AIzaSy...'" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  YOUTUBE KOL PLATFORM - Parallel Workers" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Yellow
Write-Host "    Max Channels per round: $MaxChannels"
Write-Host "    Max Videos per channel: $MaxVideos"
Write-Host "    Discovery Interval:     $DiscoveryInterval seconds ($([math]::Round($DiscoveryInterval/3600, 1)) hours)"
Write-Host "    Refresh Interval:       $RefreshInterval seconds ($([math]::Round($RefreshInterval/60, 1)) min)"
Write-Host "    Worker Start Delay:     $WorkerDelay seconds"
Write-Host "    Comments Worker:        $(if ($NoComments) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Metrics Refresh:        $(if ($NoRefresh) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Function to start a worker in new terminal
function Start-Worker {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Color
    )
    
    $title = "YouTube - $Name"
    
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

$consumerGroups = @("youtube-stats-worker-v1", "youtube-comments-worker-v1")

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

# 1. YouTube Discovery (Selenium - scrape trending shorts)
$discoveryArgs = "-m ingestion.sources.youtube_discovery --max-channels $MaxChannels --interval $DiscoveryInterval"
Start-Worker -Name "YouTube Discovery" -Command $discoveryArgs -Color "Green"

# 2. YouTube Stats Worker (API - channel + videos)
Write-Host "  ⏳ YouTube Stats Worker sẽ start sau ${WorkerDelay}s (đợi Discovery)..." -ForegroundColor Gray
$statsArgs = "-m ingestion.consumers.youtube_stats_worker --max-videos $MaxVideos --start-delay $WorkerDelay"
Start-Worker -Name "YouTube Stats Worker" -Command $statsArgs -Color "Cyan"

# 3. YouTube Comments Worker (API)
if (-not $NoComments) {
    Write-Host "  ⏳ YouTube Comments Worker sẽ start sau ${WorkerDelay}s (đợi Discovery)..." -ForegroundColor Gray
    $commentsArgs = "-m ingestion.consumers.youtube_comments_worker --max-comments 100 --start-delay $WorkerDelay"
    Start-Worker -Name "YouTube Comments Worker" -Command $commentsArgs -Color "Yellow"
}

# 4. Metrics Refresh (re-push tracked channels for velocity)
if (-not $NoRefresh) {
    $refreshArgs = "-m ingestion.sources.metrics_refresh --interval $RefreshInterval"
    Start-Worker -Name "Metrics Refresh" -Command $refreshArgs -Color "Blue"
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "  All YouTube workers started!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "  Flow:" -ForegroundColor Yellow
Write-Host "    YouTube Discovery (Selenium) → kol.discovery.raw"
Write-Host "                                         ↓"
Write-Host "                              YouTube Stats Worker (API)"
Write-Host "                                         ↓"
Write-Host "                              kol.videos.raw + kol.profiles.raw"
Write-Host "                                         ↓"
Write-Host "                              Spark Streaming (CHUNG với TikTok!)"
Write-Host "                                         ↓"
Write-Host "                              Redis: streaming_scores:{username}"
Write-Host "                                         ↓"
Write-Host "                              Dashboard (filter platform)"
Write-Host ""
Write-Host "  Tips:" -ForegroundColor Cyan
Write-Host "    - YouTube KHÔNG CẦN Selenium cho stats (100% API!)"
Write-Host "    - API Quota: 10,000 units/day (1 channel = ~102 units)"
Write-Host "    - Check Redis: docker exec kol-redis redis-cli KEYS 'streaming_scores:*'"
Write-Host "    - Filter platform in Dashboard: http://localhost:8501"
Write-Host ""

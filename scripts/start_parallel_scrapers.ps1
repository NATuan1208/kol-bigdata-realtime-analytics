<#
.SYNOPSIS
    Start KOL Scraper Pipeline - 3 Workers Song Song

.DESCRIPTION
    Flow mới (tối ưu thời gian):
    1. Scraper discovery username → push kol.discovery.raw
    2. Cả 3 workers cùng lắng nghe discovery.raw:
       - Video Stats Worker: lấy profile + video stats
       - Comment Extractor: lấy comments từ videos
       - Product Extractor: lấy products từ videos
    
    Mỗi worker dùng Chrome profile riêng (trong data/chrome_profiles/).

.EXAMPLE
    .\scripts\start_parallel_scrapers.ps1
    
.EXAMPLE
    # Chỉ chạy 2 workers (không lấy comments)
    .\scripts\start_parallel_scrapers.ps1 -NoComments
#>

param(
    [switch]$NoComments,
    [switch]$NoProducts,
    [switch]$NoVideoStats,
    [switch]$DryRun,
    [int]$MaxKols = 10,
    [int]$MaxVideos = 20,
    [int]$Interval = 300
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
Write-Host "  KOL SCRAPER PIPELINE - Parallel Workers" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Yellow
Write-Host "    Max KOLs per round: $MaxKols"
Write-Host "    Max videos per KOL: $MaxVideos"
Write-Host "    Interval: $Interval seconds"
Write-Host "    Video Stats Worker: $(if ($NoVideoStats) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Comment Extractor:  $(if ($NoComments) { 'DISABLED' } else { 'ENABLED' })"
Write-Host "    Product Extractor:  $(if ($NoProducts) { 'DISABLED' } else { 'ENABLED' })"
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

# ==================== START WORKERS ====================

Write-Host "Starting workers..." -ForegroundColor Green
Write-Host ""

# 1. Discovery Scraper (produces to kol.discovery.raw)
$discoveryArgs = "-m ingestion.sources.discovery_kol_tiktok --max-kols $MaxKols --interval $Interval"
if ($DryRun) { $discoveryArgs += " --dry-run" }
Start-Worker -Name "Discovery Scraper" -Command $discoveryArgs -Color "Green"

# 2. Video Stats Worker (consumes discovery.raw -> produces videos.raw + profiles.raw)
if (-not $NoVideoStats) {
    $videoArgs = "-m ingestion.consumers.video_stats_worker --max-videos $MaxVideos"
    if ($DryRun) { $videoArgs += " --dry-run" }
    Start-Worker -Name "Video Stats Worker" -Command $videoArgs -Color "Cyan"
}

# 3. Comment Extractor (consumes discovery.raw -> produces comments.raw)
if (-not $NoComments) {
    $commentArgs = "-m ingestion.consumers.comment_extractor --max-videos $MaxVideos"
    if ($DryRun) { $commentArgs += " --dry-run" }
    Start-Worker -Name "Comment Extractor" -Command $commentArgs -Color "Yellow"
}

# 4. Product Extractor (consumes discovery.raw -> produces products.raw)
if (-not $NoProducts) {
    $productArgs = "-m ingestion.consumers.product_extractor --max-videos $MaxVideos"
    if ($DryRun) { $productArgs += " --dry-run" }
    Start-Worker -Name "Product Extractor" -Command $productArgs -Color "Magenta"
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "  All workers started!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "  Flow:" -ForegroundColor Yellow
Write-Host "    Discovery -> discovery.raw"
Write-Host "                  |"
Write-Host "         +--------+--------+"
Write-Host "         v        v        v"
Write-Host "      Video    Comment  Product"
Write-Host "      Worker   Extract  Extract"
Write-Host "         |        |        |"
Write-Host "         v        v        v"
Write-Host "    videos.raw comments  products"
Write-Host ""
Write-Host "  Tips:" -ForegroundColor Yellow
Write-Host "    - Press Ctrl+C in each terminal to stop gracefully"
Write-Host "    - Check logs in data/logs/ folder"
Write-Host "    - View Kafka messages: http://localhost:8080 (Redpanda Console)"
Write-Host ""

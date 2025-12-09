# ============================================================================
# Build và Start Dashboard + API
# ============================================================================
# Script này build images và start containers cho Dashboard UI và API
#
# Usage:
#   .\scripts\start_dashboard.ps1
#   .\scripts\start_dashboard.ps1 -Rebuild  # Rebuild images
# ============================================================================

param(
    [switch]$Rebuild = $false
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  KOL DASHBOARD + API STARTUP" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Change to infra directory
$infraDir = Join-Path $PSScriptRoot "..\infra"
Push-Location $infraDir

try {
    # 1. Check prerequisites
    Write-Host "[1/5] Checking prerequisites..." -ForegroundColor Yellow
    
    $requiredContainers = @("kol-redis", "kol-redpanda")
    foreach ($container in $requiredContainers) {
        $running = docker ps --filter "name=$container" --filter "status=running" --format "{{.Names}}" | Select-String $container
        if (-not $running) {
            Write-Host "  ❌ Container '$container' is not running!" -ForegroundColor Red
            Write-Host "  💡 Please start infrastructure first: cd infra && docker-compose -f docker-compose.kol.yml up -d redis redpanda" -ForegroundColor Yellow
            exit 1
        }
    }
    Write-Host "  ✅ Prerequisites OK" -ForegroundColor Green
    
    # 2. Build images (if needed)
    if ($Rebuild) {
        Write-Host ""
        Write-Host "[2/5] Building Docker images..." -ForegroundColor Yellow
        docker-compose -f docker-compose.kol.yml build api dashboard
        Write-Host "  ✅ Images built" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[2/5] Skipping build (use -Rebuild to rebuild)" -ForegroundColor Yellow
    }
    
    # 3. Start API
    Write-Host ""
    Write-Host "[3/5] Starting FastAPI backend..." -ForegroundColor Yellow
    docker-compose -f docker-compose.kol.yml up -d api
    
    # Wait for API to be healthy
    Write-Host "  ⏳ Waiting for API to be ready..." -ForegroundColor Yellow
    $maxRetries = 30
    $retries = 0
    $apiReady = $false
    
    while ($retries -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/healthz" -Method GET -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                $apiReady = $true
                break
            }
        } catch {
            # Ignore errors
        }
        Start-Sleep -Seconds 2
        $retries++
        Write-Host "    Attempt $retries/$maxRetries..." -ForegroundColor Gray
    }
    
    if ($apiReady) {
        Write-Host "  ✅ API is ready at http://localhost:8000" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  API health check timeout (but may still be starting)" -ForegroundColor Yellow
    }
    
    # 4. Start Dashboard
    Write-Host ""
    Write-Host "[4/5] Starting Streamlit dashboard..." -ForegroundColor Yellow
    docker-compose -f docker-compose.kol.yml up -d dashboard
    Write-Host "  ✅ Dashboard started" -ForegroundColor Green
    
    # 5. Show status
    Write-Host ""
    Write-Host "[5/5] Services status:" -ForegroundColor Yellow
    docker-compose -f docker-compose.kol.yml ps api dashboard
    
    # Success message
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✅ DASHBOARD + API STARTED" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Access URLs:" -ForegroundColor Cyan
    Write-Host "  • Dashboard UI:  http://localhost:8501" -ForegroundColor White
    Write-Host "  • API Docs:      http://localhost:8000/docs" -ForegroundColor White
    Write-Host "  • API Health:    http://localhost:8000/healthz" -ForegroundColor White
    Write-Host ""
    Write-Host "📝 View logs:" -ForegroundColor Cyan
    Write-Host "  docker logs -f kol-dashboard" -ForegroundColor Gray
    Write-Host "  docker logs -f kol-api" -ForegroundColor Gray
    Write-Host ""
    Write-Host "🛑 Stop services:" -ForegroundColor Cyan
    Write-Host "  docker-compose -f docker-compose.kol.yml stop api dashboard" -ForegroundColor Gray
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}

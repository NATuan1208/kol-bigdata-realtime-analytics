# ============================================================================
# KOL Platform - DDL Setup Script (PowerShell)
# ============================================================================
# This script verifies and displays all Trino tables for the KOL Analytics Platform
# 
# Usage:
#   .\setup_tables.ps1
# ============================================================================

Write-Host "=============================================="  -ForegroundColor Cyan
Write-Host "🗄️  KOL Platform - Verifying Trino Tables"  -ForegroundColor Cyan
Write-Host "=============================================="  -ForegroundColor Cyan

# Check if Trino is running
$trinoRunning = docker ps | Select-String "sme-trino"
if (-not $trinoRunning) {
    Write-Host "❌ Error: sme-trino container is not running" -ForegroundColor Red
    Write-Host "   Start it with: docker-compose -f dwh/infra/docker-compose.kol.yml up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "📋 Listing tables in each schema..." -ForegroundColor Yellow

Write-Host ""
Write-Host "--- BRONZE LAYER ---" -ForegroundColor Green
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_bronze" 2>$null

Write-Host ""
Write-Host "--- SILVER LAYER ---" -ForegroundColor Green
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_silver" 2>$null

Write-Host ""
Write-Host "--- GOLD LAYER ---" -ForegroundColor Green
docker exec sme-trino trino --execute "SHOW TABLES FROM minio.kol_gold" 2>$null

Write-Host ""
Write-Host "=============================================="  -ForegroundColor Cyan
Write-Host "📊 Record Counts (Key Tables):"  -ForegroundColor Cyan
Write-Host "=============================================="  -ForegroundColor Cyan

Write-Host ""
Write-Host "BRONZE:" -ForegroundColor Yellow
$counts = @(
    @{Table="twitter_human_bots"; Query="SELECT COUNT(*) FROM minio.kol_bronze.twitter_human_bots"},
    @{Table="short_video_trends"; Query="SELECT COUNT(*) FROM minio.kol_bronze.short_video_trends"}
)

foreach ($item in $counts) {
    $result = docker exec sme-trino trino --execute $item.Query 2>$null
    Write-Host "  $($item.Table): $result"
}

Write-Host ""
Write-Host "SILVER:" -ForegroundColor Yellow
$silverCounts = @(
    @{Table="kol_profiles"; Query="SELECT COUNT(*) FROM minio.kol_silver.kol_profiles"},
    @{Table="kol_trust_features"; Query="SELECT COUNT(*) FROM minio.kol_silver.kol_trust_features"},
    @{Table="kol_content"; Query="SELECT COUNT(*) FROM minio.kol_silver.kol_content"}
)

foreach ($item in $silverCounts) {
    $result = docker exec sme-trino trino --execute $item.Query 2>$null
    Write-Host "  $($item.Table): $result"
}

Write-Host ""
Write-Host "GOLD:" -ForegroundColor Yellow
$goldCounts = @(
    @{Table="dim_kol"; Query="SELECT COUNT(*) FROM minio.kol_gold.dim_kol"},
    @{Table="ml_trust_features_engineered"; Query="SELECT COUNT(*) FROM minio.kol_gold.ml_trust_features_engineered"},
    @{Table="fact_kol_performance"; Query="SELECT COUNT(*) FROM minio.kol_gold.fact_kol_performance"}
)

foreach ($item in $goldCounts) {
    $result = docker exec sme-trino trino --execute $item.Query 2>$null
    Write-Host "  $($item.Table): $result"
}

Write-Host ""
Write-Host "=============================================="  -ForegroundColor Cyan
Write-Host "✅ Verification complete!"  -ForegroundColor Green
Write-Host "=============================================="  -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick commands:" -ForegroundColor Yellow
Write-Host "  Query data:     docker exec -it sme-trino trino"
Write-Host "  Train models:   docker exec kol-trainer python -m models.trust.train_xgb"
Write-Host "  Evaluate:       docker exec kol-trainer python -m models.trust.evaluate --save-report"

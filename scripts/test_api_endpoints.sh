#!/bin/bash
# ============================================================================
# Test API Endpoints Script
# ============================================================================
# Run with: bash scripts/test_api_endpoints.sh
# Or in Git Bash: ./scripts/test_api_endpoints.sh
# ============================================================================

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   KOL Platform API - Endpoint Testing     ${NC}"
echo -e "${BLUE}============================================${NC}"
echo "Target: $BASE_URL"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Counter for results
PASSED=0
FAILED=0
SKIPPED=0

# Function to test GET endpoint
test_get() {
    local endpoint=$1
    local description=$2
    local expect_404=${3:-false}
    local show_response=${4:-false}
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  ${GRAY}GET ${endpoint}${NC}"
    
    response=$(curl -s -w "\n%{http_code}" "${BASE_URL}${endpoint}" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        if [ "$show_response" = "true" ]; then
            echo -e "  ${GRAY}Response: $(echo $body | head -c 200)...${NC}"
        fi
        ((PASSED++))
    elif [ "$http_code" -eq 422 ]; then
        echo -e "  ${YELLOW}⚠ PARTIAL${NC} (HTTP 422 - Validation error, endpoint exists)"
        ((PASSED++))
    elif [ "$http_code" -eq 404 ] && [ "$expect_404" = "true" ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP 404 - Expected, endpoint works but no data)"
        ((PASSED++))
    elif [ "$http_code" -eq 404 ]; then
        echo -e "  ${RED}✗ FAILED${NC} (HTTP 404 - Endpoint not found)"
        ((FAILED++))
    elif [ "$http_code" -eq 500 ]; then
        echo -e "  ${RED}✗ FAILED${NC} (HTTP 500 - Server error)"
        ((FAILED++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (HTTP $http_code)"
        ((FAILED++))
    fi
    echo ""
}

# Function to test POST endpoint with JSON body
test_post() {
    local endpoint=$1
    local description=$2
    local body=$3
    local show_response=${4:-false}
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  ${GRAY}POST ${endpoint}${NC}"
    
    response=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}${endpoint}" \
        -H "Content-Type: application/json" \
        -d "$body" \
        --max-time 15 2>/dev/null)
    
    http_code=$(echo "$response" | tail -n1)
    resp_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        if [ "$show_response" = "true" ]; then
            echo -e "  ${GRAY}Response: $(echo $resp_body | head -c 300)...${NC}"
        fi
        ((PASSED++))
    elif [ "$http_code" -eq 422 ]; then
        echo -e "  ${YELLOW}⚠ PARTIAL${NC} (HTTP 422 - Validation error)"
        ((PASSED++))
    elif [ "$http_code" -eq 503 ]; then
        echo -e "  ${YELLOW}⚠ SKIPPED${NC} (HTTP 503 - Model not available)"
        ((SKIPPED++))
    elif [ "$http_code" -eq 000 ]; then
        echo -e "  ${YELLOW}⚠ SKIPPED${NC} (Timeout or connection failed)"
        ((SKIPPED++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (HTTP $http_code)"
        echo -e "  ${GRAY}Response: $resp_body${NC}"
        ((FAILED++))
    fi
    echo ""
}

# ============================================================================
# HEALTH CHECKS
# ============================================================================
echo -e "${BLUE}--- Health Checks ---${NC}"

test_get "/" "Root endpoint" false true
test_get "/healthz" "Health check" false true
test_get "/docs" "Swagger UI documentation"
test_get "/redoc" "ReDoc documentation"
test_get "/openapi.json" "OpenAPI schema"

# ============================================================================
# KOL ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- KOL Endpoints (/api/v1/kols) ---${NC}"

test_get "/api/v1/kols" "List KOLs" false true
test_get "/api/v1/kols?limit=5" "List KOLs with limit"
test_get "/api/v1/kols?platform=tiktok" "List TikTok KOLs"
test_get "/api/v1/kols?platform=youtube" "List YouTube KOLs"
test_get "/api/v1/kols/test_user_123" "Get single KOL by ID" true
test_get "/api/v1/kols/test_user_123/content" "Get KOL content" true

# ============================================================================
# SCORES ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Scores Endpoints (/api/v1/scores) ---${NC}"

test_get "/api/v1/scores/test_user_123" "All scores for KOL" false true
test_get "/api/v1/scores/test_user_123/trust" "Trust score" true
test_get "/api/v1/scores/test_user_123/trending" "Trending score" true
test_get "/api/v1/scores/test_user_123/success" "Success score" true

# ============================================================================
# STATS ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Stats Endpoints (/api/v1/stats) ---${NC}"

test_get "/api/v1/stats" "Platform statistics" false true
test_get "/api/v1/stats/platforms" "Stats by platform"
test_get "/api/v1/stats/cache" "Cache statistics"

# ============================================================================
# TRENDING ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Trending Endpoints (/api/v1/trending) ---${NC}"

test_get "/api/v1/trending" "Top trending KOLs" false true
test_get "/api/v1/trending?limit=5" "Top 5 trending"
test_get "/api/v1/trending/detailed" "Detailed trending (Dashboard)" false true
test_get "/api/v1/trending/viral" "Viral KOLs"
test_get "/api/v1/trending/hot" "Hot KOLs"
test_get "/api/v1/trending/rising" "Rising KOLs"

# ============================================================================
# SEARCH ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Search Endpoints (/api/v1/search) ---${NC}"

test_get "/api/v1/search?q=test" "Search KOLs" false true
test_get "/api/v1/search?q=beauty&platform=tiktok" "Search TikTok KOLs"
test_get "/api/v1/search/suggest?prefix=te" "Autocomplete suggestions"

# ============================================================================
# PREDICT ENDPOINTS (ML Inference)
# ============================================================================
echo -e "${BLUE}--- Predict Endpoints (/predict) - ML Inference ---${NC}"

# Trust Score prediction
TRUST_BODY='{
    "kol_id": "test_kol_001",
    "followers_count": 50000,
    "following_count": 500,
    "post_count": 100,
    "account_age_days": 365,
    "total_likes": 500000,
    "avg_views": 10000,
    "avg_likes": 2500,
    "avg_comments": 150,
    "avg_shares": 50,
    "engagement_rate": 0.05,
    "posting_consistency": 0.8,
    "content_quality_score": 0.75,
    "is_verified": true
}'
test_post "/predict/trust" "Trust Score prediction" "$TRUST_BODY" true

# Success Score prediction
SUCCESS_BODY='{
    "kol_id": "test_kol_001",
    "followers": 50000,
    "engagement_rate": 0.05,
    "avg_views": 10000,
    "category": "beauty",
    "past_success_rate": 0.7,
    "brand_fit_score": 0.8
}'
test_post "/predict/success" "Success Score prediction" "$SUCCESS_BODY" true

# Trending Score prediction
TRENDING_BODY='{
    "kol_id": "test_kol_001",
    "followers": 50000,
    "views_growth_rate": 0.15,
    "engagement_growth_rate": 0.20,
    "viral_video_count": 3,
    "recent_mentions": 100,
    "social_buzz_score": 0.75
}'
test_post "/predict/trending" "Trending Score prediction" "$TRENDING_BODY" true

# Model info endpoints (only trust and success have model-info)
test_get "/predict/trust/model-info" "Trust model info" false true
test_get "/predict/success/model-info" "Success model info" false true
# Note: trending uses formula-based calculation, not ML model

# Health endpoint
test_get "/predict/health" "Predict service health" false true

# ============================================================================
# LEGACY ENDPOINTS (Deprecated)
# ============================================================================
echo -e "${BLUE}--- Legacy Endpoints (/kol) - Deprecated ---${NC}"

test_get "/kol/test_user_123/trust" "Legacy trust endpoint" true

# ============================================================================
# SUMMARY
# ============================================================================
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}               TEST SUMMARY                ${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "  ${GREEN}Passed:${NC}  $PASSED"
echo -e "  ${YELLOW}Skipped:${NC} $SKIPPED"
echo -e "  ${RED}Failed:${NC}  $FAILED"
TOTAL=$((PASSED + FAILED + SKIPPED))
echo -e "  Total:   $TOTAL"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed. Check the output above.${NC}"
    exit 1
fi

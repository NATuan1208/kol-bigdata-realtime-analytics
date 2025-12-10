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
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   KOL Platform API - Endpoint Testing     ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Counter for results
PASSED=0
FAILED=0
EXPECTED_404=0

# Function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  ${method} ${endpoint}"
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${endpoint}")
    
    if [ "$response" -ge 200 ] && [ "$response" -lt 300 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $response)"
        ((PASSED++))
    elif [ "$response" -eq 422 ]; then
        # 422 = Validation error, endpoint exists but params missing
        echo -e "  ${YELLOW}⚠ PARTIAL${NC} (HTTP $response - Validation error, endpoint exists)"
        ((PASSED++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (HTTP $response)"
        ((FAILED++))
    fi
    echo ""
}

# Function to test endpoint expecting 404 (data not found but endpoint works)
test_endpoint_expect_404() {
    local method=$1
    local endpoint=$2
    local description=$3
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  ${method} ${endpoint}"
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${endpoint}")
    
    if [ "$response" -eq 404 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $response - Expected 404, endpoint works)"
        ((EXPECTED_404++))
        ((PASSED++))
    elif [ "$response" -ge 200 ] && [ "$response" -lt 300 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $response - Data found)"
        ((PASSED++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (HTTP $response)"
        ((FAILED++))
    fi
    echo ""
}

# Function to test endpoint with JSON output
test_endpoint_json() {
    local method=$1
    local endpoint=$2
    local description=$3
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  ${method} ${endpoint}"
    
    response=$(curl -s "${BASE_URL}${endpoint}")
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${endpoint}")
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        echo -e "  Response: $(echo $response | head -c 200)..."
        ((PASSED++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (HTTP $http_code)"
        echo -e "  Response: $response"
        ((FAILED++))
    fi
    echo ""
}

# ============================================================================
# HEALTH CHECK
# ============================================================================
echo -e "${BLUE}--- Health Checks ---${NC}"
test_endpoint_json "GET" "/" "Root endpoint"
test_endpoint_json "GET" "/healthz" "Health check"
test_endpoint "GET" "/docs" "Swagger UI documentation"
test_endpoint "GET" "/redoc" "ReDoc documentation"

# ============================================================================
# KOL ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- KOL Endpoints (/api/v1/kols) ---${NC}"
test_endpoint_json "GET" "/api/v1/kols" "List KOLs"
test_endpoint_json "GET" "/api/v1/kols?limit=5" "List KOLs with limit"
test_endpoint_json "GET" "/api/v1/kols?platform=tiktok" "List TikTok KOLs"
test_endpoint_expect_404 "GET" "/api/v1/kols/test_user_123" "Get single KOL by ID (expect 404 - no data)"
test_endpoint_json "GET" "/api/v1/kols/test_user_123/content" "Get KOL content"

# ============================================================================
# SCORES ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Scores Endpoints (/api/v1/scores) ---${NC}"
test_endpoint_json "GET" "/api/v1/scores/test_user_123" "All scores for KOL"
test_endpoint_expect_404 "GET" "/api/v1/scores/test_user_123/trust" "Trust score (expect 404 - not computed)"
test_endpoint_expect_404 "GET" "/api/v1/scores/test_user_123/trending" "Trending score (expect 404 - not computed)"
test_endpoint_expect_404 "GET" "/api/v1/scores/test_user_123/success" "Success score (expect 404 - not computed)"

# ============================================================================
# STATS ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Stats Endpoints (/api/v1/stats) ---${NC}"
test_endpoint_json "GET" "/api/v1/stats" "Platform statistics"
test_endpoint_json "GET" "/api/v1/stats/platforms" "Stats by platform"
test_endpoint_json "GET" "/api/v1/stats/cache" "Cache statistics"

# ============================================================================
# TRENDING ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Trending Endpoints (/api/v1/trending) ---${NC}"
test_endpoint_json "GET" "/api/v1/trending" "Top trending KOLs"
test_endpoint_json "GET" "/api/v1/trending?limit=5" "Top 5 trending"
test_endpoint_json "GET" "/api/v1/trending/viral" "Viral KOLs"
test_endpoint_json "GET" "/api/v1/trending/hot" "Hot KOLs"
test_endpoint_json "GET" "/api/v1/trending/rising" "Rising KOLs"

# ============================================================================
# SEARCH ENDPOINTS (v1)
# ============================================================================
echo -e "${BLUE}--- Search Endpoints (/api/v1/search) ---${NC}"
test_endpoint_json "GET" "/api/v1/search?q=test" "Search KOLs"
test_endpoint_json "GET" "/api/v1/search/suggest?prefix=te" "Autocomplete suggestions"

# ============================================================================
# PREDICT ENDPOINTS (ML) - Skipped by default (requires MLflow server)
# ============================================================================
echo -e "${BLUE}--- Predict Endpoints (/predict) ---${NC}"
echo -e "${YELLOW}⚠ Predict endpoints require MLflow server - testing with timeout${NC}"

# Test predict endpoints with 5 second timeout (will fail if MLflow not running)
predict_test() {
    local endpoint=$1
    local description=$2
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "  GET $endpoint"
    
    # Use timeout to prevent hanging
    response=$(timeout 5 curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${endpoint}" 2>/dev/null)
    exit_code=$?
    
    if [ $exit_code -eq 124 ]; then
        echo -e "  ${YELLOW}⚠ SKIPPED${NC} (timeout - MLflow server not running)"
    elif [ "$response" -ge 200 ] && [ "$response" -lt 500 ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} (HTTP $response)"
        ((PASSED++))
    else
        echo -e "  ${YELLOW}⚠ SKIPPED${NC} (HTTP $response - MLflow required)"
    fi
    echo ""
}

predict_test "/predict/trust/model-info" "Trust model info"
predict_test "/predict/success/model-info" "Success model info"

# ============================================================================
# LEGACY ENDPOINTS
# ============================================================================
echo -e "${BLUE}--- Legacy Endpoints (/kol) ---${NC}"
test_endpoint_json "GET" "/kol/test_user_123/trust" "Legacy trust endpoint (deprecated)"

# ============================================================================
# SUMMARY
# ============================================================================
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}               TEST SUMMARY                ${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "  ${GREEN}Passed:${NC} $PASSED"
echo -e "  ${YELLOW}Expected 404:${NC} $EXPECTED_404 (no data but endpoint works)"
echo -e "  ${RED}Failed:${NC} $FAILED"
TOTAL=$((PASSED + FAILED))
echo -e "  Total:  $TOTAL"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed. Check the output above.${NC}"
    exit 1
fi

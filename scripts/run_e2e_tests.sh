#!/bin/bash
# ============================================
# E2E Test Runner for KOL Analytics Platform
# ============================================
# 
# Usage:
#   ./scripts/run_e2e_tests.sh              # Run all tests
#   ./scripts/run_e2e_tests.sh --phase 1    # Run Phase 1 only
#   ./scripts/run_e2e_tests.sh --phase 3    # Run Phase 3 only
#   ./scripts/run_e2e_tests.sh --verbose    # Verbose output
#
# Prerequisites:
#   - Docker containers running (kol-redpanda, kol-redis, kol-api, kol-spark-master)
#   - Streaming job should be running for Phase 2 hot path tests
#
# Author: KOL Analytics Team
# Date: December 2025
# ============================================

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
PASSED=0
FAILED=0
SKIPPED=0
TOTAL=0

# Configuration
VERBOSE=false
PHASE_FILTER=""
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-16379}"
KAFKA_CONTAINER="${KAFKA_CONTAINER:-kol-redpanda}"
REDIS_CONTAINER="${REDIS_CONTAINER:-kol-redis}"
API_CONTAINER="${API_CONTAINER:-kol-api}"
SPARK_CONTAINER="${SPARK_CONTAINER:-kol-spark-master}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --phase)
            PHASE_FILTER="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--phase N] [--verbose]"
            echo ""
            echo "Options:"
            echo "  --phase N    Run only phase N (1-4)"
            echo "  --verbose    Show detailed output"
            echo "  --help       Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to log
log() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

# Function to run a test
run_test() {
    local test_id=$1
    local test_name=$2
    local test_cmd=$3
    local timeout=${4:-30}
    
    TOTAL=$((TOTAL + 1))
    printf "  [%-8s] %-50s " "$test_id" "$test_name"
    
    # Run test with timeout
    if timeout "$timeout" bash -c "$test_cmd" > /tmp/test_output_$$ 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        PASSED=$((PASSED + 1))
        if [ "$VERBOSE" = true ] && [ -s /tmp/test_output_$$ ]; then
            echo -e "           Output: $(cat /tmp/test_output_$$)"
        fi
        rm -f /tmp/test_output_$$
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        FAILED=$((FAILED + 1))
        if [ -s /tmp/test_output_$$ ]; then
            echo -e "           ${RED}Error: $(cat /tmp/test_output_$$ | head -3)${NC}"
        fi
        rm -f /tmp/test_output_$$
        return 1
    fi
}

# Function to skip a test
skip_test() {
    local test_id=$1
    local test_name=$2
    local reason=$3
    
    TOTAL=$((TOTAL + 1))
    SKIPPED=$((SKIPPED + 1))
    printf "  [%-8s] %-50s " "$test_id" "$test_name"
    echo -e "${YELLOW}⏭️  SKIP${NC} ($reason)"
}

# Function to check if container is running
check_container() {
    docker ps --filter "name=$1" --filter "status=running" --format "{{.Names}}" | grep -q "$1"
}

# ============================================
# PHASE 1: INGESTION VALIDATION
# ============================================
run_phase_1() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📋 PHASE 1: INGESTION VALIDATION${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Check if Kafka container is running
    if ! check_container "$KAFKA_CONTAINER"; then
        skip_test "ING-001" "Kafka container running" "Container $KAFKA_CONTAINER not found"
        skip_test "ING-002" "Videos topic exists" "Kafka unavailable"
        skip_test "ING-003" "Profiles topic exists" "Kafka unavailable"
        skip_test "ING-004" "Products topic exists" "Kafka unavailable"
        skip_test "ING-005" "Comments topic exists" "Kafka unavailable"
        skip_test "ING-006" "Discovery topic exists" "Kafka unavailable"
        return
    fi
    
    run_test "ING-001" "Kafka container running" \
        "check_container $KAFKA_CONTAINER"
    
    run_test "ING-002" "Videos topic exists" \
        "docker exec $KAFKA_CONTAINER rpk topic list 2>/dev/null | grep -q 'kol.videos.raw'"
    
    run_test "ING-003" "Profiles topic exists" \
        "docker exec $KAFKA_CONTAINER rpk topic list 2>/dev/null | grep -q 'kol.profiles.raw'"
    
    run_test "ING-004" "Products topic exists" \
        "docker exec $KAFKA_CONTAINER rpk topic list 2>/dev/null | grep -q 'kol.products.raw'"
    
    run_test "ING-005" "Comments topic exists" \
        "docker exec $KAFKA_CONTAINER rpk topic list 2>/dev/null | grep -q 'kol.comments.raw'"
    
    run_test "ING-006" "Discovery topic exists" \
        "docker exec $KAFKA_CONTAINER rpk topic list 2>/dev/null | grep -q 'kol.discovery.raw'"
    
    run_test "ING-007" "Videos topic has messages" \
        "docker exec $KAFKA_CONTAINER rpk topic describe kol.videos.raw 2>/dev/null | grep -qE 'PARTITION|OFFSET'"
}

# ============================================
# PHASE 2: PIPELINE INTEGRITY
# ============================================
run_phase_2() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📋 PHASE 2: PIPELINE INTEGRITY${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Check if Redis container is running
    if ! check_container "$REDIS_CONTAINER"; then
        skip_test "HOT-001" "Redis container running" "Container $REDIS_CONTAINER not found"
        skip_test "HOT-002" "Redis has trending keys" "Redis unavailable"
        skip_test "HOT-003" "Redis ranking sorted set exists" "Redis unavailable"
        skip_test "HOT-004" "Trending scores are valid" "Redis unavailable"
        return
    fi
    
    run_test "HOT-001" "Redis container running" \
        "check_container $REDIS_CONTAINER"
    
    run_test "HOT-002" "Redis is healthy (PING)" \
        "docker exec $REDIS_CONTAINER redis-cli PING 2>/dev/null | grep -q 'PONG'"
    
    run_test "HOT-003" "Redis has trending keys" \
        "docker exec $REDIS_CONTAINER redis-cli KEYS 'trending:*' 2>/dev/null | grep -q 'trending'"
    
    run_test "HOT-004" "Redis has streaming_scores keys" \
        "docker exec $REDIS_CONTAINER redis-cli KEYS 'streaming_scores:*' 2>/dev/null | grep -q 'streaming_scores'"
    
    run_test "HOT-005" "Redis ranking sorted set exists" \
        "docker exec $REDIS_CONTAINER redis-cli EXISTS 'ranking:tiktok:trending' 2>/dev/null | grep -q '1'"
    
    run_test "HOT-006" "Trending scores in valid range (0-100)" \
        "docker exec $REDIS_CONTAINER redis-cli ZREVRANGE 'ranking:tiktok:trending' 0 0 WITHSCORES 2>/dev/null | tail -1 | awk '{if(\$1>=0 && \$1<=100) exit 0; else exit 1}'" 10
    
    # Check Spark container
    if check_container "$SPARK_CONTAINER"; then
        run_test "COLD-001" "Spark master is accessible" \
            "docker exec $SPARK_CONTAINER curl -sf http://localhost:8080 2>/dev/null | grep -qi 'spark'"
    else
        skip_test "COLD-001" "Spark master is accessible" "Container $SPARK_CONTAINER not found"
    fi
}

# ============================================
# PHASE 3: ML INFERENCE
# ============================================
run_phase_3() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📋 PHASE 3: ML INFERENCE${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Check if API is accessible
    if ! curl -sf "$API_BASE_URL/healthz" > /dev/null 2>&1; then
        skip_test "ML-001" "API health check" "API not accessible at $API_BASE_URL"
        skip_test "ML-002" "Trust score prediction" "API unavailable"
        skip_test "ML-003" "Success score prediction" "API unavailable"
        skip_test "ML-004" "Trending score calculation" "API unavailable"
        skip_test "ML-005" "Trust model info" "API unavailable"
        skip_test "ML-006" "Success model info" "API unavailable"
        skip_test "ML-007" "API response time < 100ms" "API unavailable"
        return
    fi
    
    run_test "ML-001" "API health check" \
        "curl -sf '$API_BASE_URL/healthz' | grep -q 'ok'"
    
    run_test "ML-002" "Trust score prediction" \
        "curl -sf -X POST '$API_BASE_URL/predict/trust' \
            -H 'Content-Type: application/json' \
            -d '{\"kol_id\":\"test_e2e\",\"followers_count\":10000,\"following_count\":100,\"post_count\":50,\"favorites_count\":5000,\"account_age_days\":100,\"verified\":false,\"has_bio\":true,\"has_url\":false,\"has_profile_image\":true,\"bio_length\":20}' \
            | grep -q 'trust_score'"
    
    run_test "ML-003" "Success score prediction" \
        "curl -sf -X POST '$API_BASE_URL/predict/success' \
            -H 'Content-Type: application/json' \
            -d '{\"kol_id\":\"test_e2e\",\"video_views\":10000,\"video_likes\":500,\"video_comments\":50,\"video_shares\":20,\"engagement_total\":570,\"engagement_rate\":0.057,\"est_clicks\":100,\"est_ctr\":0.01,\"price\":50000}' \
            | grep -q 'success_score'"
    
    run_test "ML-004" "Trending score calculation" \
        "curl -sf -X POST '$API_BASE_URL/predict/trending' \
            -H 'Content-Type: application/json' \
            -d '{\"kol_id\":\"test_e2e\",\"current_velocity\":50,\"baseline_velocity\":10,\"global_avg_velocity\":20,\"momentum\":0.5}' \
            | grep -q 'trending_score'"
    
    run_test "ML-005" "Trust model info endpoint" \
        "curl -sf '$API_BASE_URL/predict/trust/model-info' | grep -q 'model_name'"
    
    run_test "ML-006" "Success model info endpoint" \
        "curl -sf '$API_BASE_URL/predict/success/model-info' | grep -q 'model_type'"
    
    # Response time test - capture time and check if < 100ms (0.1s)
    run_test "ML-007" "API response time < 100ms" \
        "response_time=\$(curl -o /dev/null -s -w '%{time_total}' '$API_BASE_URL/healthz'); \
         awk -v rt=\"\$response_time\" 'BEGIN{if(rt < 0.1) exit 0; else exit 1}'"
    
    run_test "ML-008" "Trending API endpoint" \
        "curl -sf '$API_BASE_URL/api/v1/trending' | grep -q 'data'"
    
    run_test "ML-009" "Trust score in valid range" \
        "score=\$(curl -sf -X POST '$API_BASE_URL/predict/trust' \
            -H 'Content-Type: application/json' \
            -d '{\"kol_id\":\"range_test\",\"followers_count\":50000,\"following_count\":200,\"post_count\":100,\"favorites_count\":25000,\"account_age_days\":365,\"verified\":true,\"has_bio\":true,\"has_url\":true,\"has_profile_image\":true,\"bio_length\":100}' \
            | grep -o '\"trust_score\":[0-9.]*' | cut -d: -f2); \
         awk -v s=\"\$score\" 'BEGIN{if(s >= 0 && s <= 100) exit 0; else exit 1}'"
}

# ============================================
# PHASE 4: VISUALIZATION
# ============================================
run_phase_4() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📋 PHASE 4: VISUALIZATION${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Check Streamlit dashboard
    if curl -sf "http://localhost:8501" > /dev/null 2>&1; then
        run_test "VIZ-001" "Streamlit dashboard accessible" \
            "curl -sf -o /dev/null 'http://localhost:8501'"
    else
        skip_test "VIZ-001" "Streamlit dashboard accessible" "Dashboard not running at localhost:8501"
    fi
    
    # Check API endpoints used by dashboard
    run_test "VIZ-002" "Root endpoint returns API info" \
        "curl -sf '$API_BASE_URL/' | grep -q 'KOL Platform API'"
    
    run_test "VIZ-003" "Swagger UI accessible" \
        "curl -sf -o /dev/null '$API_BASE_URL/docs'"
    
    run_test "VIZ-004" "ReDoc accessible" \
        "curl -sf -o /dev/null '$API_BASE_URL/redoc'"
}

# ============================================
# MAIN EXECUTION
# ============================================
main() {
    echo ""
    echo "========================================"
    echo "  KOL ANALYTICS PLATFORM E2E TEST"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""
    echo "Configuration:"
    echo "  API URL:        $API_BASE_URL"
    echo "  Kafka Container: $KAFKA_CONTAINER"
    echo "  Redis Container: $REDIS_CONTAINER"
    echo "  Verbose:        $VERBOSE"
    if [ -n "$PHASE_FILTER" ]; then
        echo "  Phase Filter:   $PHASE_FILTER"
    fi
    
    # Run phases based on filter
    if [ -z "$PHASE_FILTER" ] || [ "$PHASE_FILTER" = "1" ]; then
        run_phase_1
    fi
    
    if [ -z "$PHASE_FILTER" ] || [ "$PHASE_FILTER" = "2" ]; then
        run_phase_2
    fi
    
    if [ -z "$PHASE_FILTER" ] || [ "$PHASE_FILTER" = "3" ]; then
        run_phase_3
    fi
    
    if [ -z "$PHASE_FILTER" ] || [ "$PHASE_FILTER" = "4" ]; then
        run_phase_4
    fi
    
    # Summary
    echo ""
    echo "========================================"
    echo "  TEST SUMMARY"
    echo "========================================"
    echo "  Total:   $TOTAL"
    echo -e "  Passed:  ${GREEN}$PASSED${NC}"
    echo -e "  Failed:  ${RED}$FAILED${NC}"
    echo -e "  Skipped: ${YELLOW}$SKIPPED${NC}"
    if [ $TOTAL -gt 0 ]; then
        # Use shell arithmetic (bc may not be available)
        PASS_RATE=$((PASSED * 100 / TOTAL))
        echo "  Rate:    ${PASS_RATE}%"
    fi
    echo "========================================"
    
    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
        exit 0
    else
        echo -e "${RED}❌ SOME TESTS FAILED${NC}"
        exit 1
    fi
}

# Export check_container function for use in subshells
export -f check_container

# Run main
main

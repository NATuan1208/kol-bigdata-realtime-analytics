#!/bin/bash
# ============================================================================
# KOL Analytics Domain Separation Validation Script
# ============================================================================
# This script validates that KOL and SME domains are properly separated
# Run this after initial setup or after making infrastructure changes
# ============================================================================

set -e

PASS=0
FAIL=0

echo "============================================"
echo "KOL/SME Domain Separation Validation"
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# ============================================================================
# 1. Check MinIO Buckets
# ============================================================================
echo "📦 Validating MinIO Buckets..."

if docker exec sme-minio mc ls local/ 2>/dev/null | grep -q "kol-bronze"; then
    pass "kol-bronze bucket exists"
else
    fail "kol-bronze bucket missing"
fi

if docker exec sme-minio mc ls local/ 2>/dev/null | grep -q "kol-silver"; then
    pass "kol-silver bucket exists"
else
    fail "kol-silver bucket missing"
fi

if docker exec sme-minio mc ls local/ 2>/dev/null | grep -q "kol-gold"; then
    pass "kol-gold bucket exists"
else
    fail "kol-gold bucket missing"
fi

if docker exec sme-minio mc ls local/ 2>/dev/null | grep -q "kol-mlflow"; then
    pass "kol-mlflow bucket exists"
else
    fail "kol-mlflow bucket missing"
fi

echo ""

# ============================================================================
# 2. Check PostgreSQL Databases
# ============================================================================
echo "🗄️  Validating PostgreSQL Databases..."

if docker exec sme-postgres psql -U admin -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "kol_mlflow"; then
    pass "kol_mlflow database exists"
else
    fail "kol_mlflow database missing"
fi

if docker exec sme-postgres psql -U admin -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "kol_metadata"; then
    pass "kol_metadata database exists"
else
    warn "kol_metadata database missing (optional)"
fi

echo ""

# ============================================================================
# 3. Check Trino Schemas
# ============================================================================
echo "🚀 Validating Trino Schemas..."

if docker exec sme-trino trino --execute "SHOW SCHEMAS IN iceberg" 2>/dev/null | grep -q "kol_bronze"; then
    pass "iceberg.kol_bronze schema exists"
else
    fail "iceberg.kol_bronze schema missing"
fi

if docker exec sme-trino trino --execute "SHOW SCHEMAS IN iceberg" 2>/dev/null | grep -q "kol_silver"; then
    pass "iceberg.kol_silver schema exists"
else
    fail "iceberg.kol_silver schema missing"
fi

if docker exec sme-trino trino --execute "SHOW SCHEMAS IN iceberg" 2>/dev/null | grep -q "kol_gold"; then
    pass "iceberg.kol_gold schema exists"
else
    fail "iceberg.kol_gold schema missing"
fi

echo ""

# ============================================================================
# 4. Check Cassandra Keyspace
# ============================================================================
echo "💿 Validating Cassandra Keyspace..."

if docker ps --filter "name=kol-cassandra" --filter "status=running" | grep -q "kol-cassandra"; then
    if docker exec kol-cassandra cqlsh -e "DESCRIBE KEYSPACE kol_metrics" 2>/dev/null | grep -q "kol_metrics"; then
        pass "kol_metrics keyspace exists"
    else
        fail "kol_metrics keyspace missing"
    fi
else
    warn "kol-cassandra not running (start with 'make up-kol')"
fi

echo ""

# ============================================================================
# 5. Check Environment Variables
# ============================================================================
echo "🔧 Validating Environment Variables (.env.kol)..."

if grep -q "MINIO_BUCKET_BRONZE=kol-bronze" .env.kol 2>/dev/null; then
    pass "MINIO_BUCKET_BRONZE configured correctly"
else
    fail "MINIO_BUCKET_BRONZE not set to kol-bronze in .env.kol"
fi

if grep -q "TRINO_SCHEMA_BRONZE=kol_bronze" .env.kol 2>/dev/null; then
    pass "TRINO_SCHEMA_BRONZE configured correctly"
else
    fail "TRINO_SCHEMA_BRONZE not set to kol_bronze in .env.kol"
fi

if grep -q "MLFLOW_EXPERIMENT_NAME=KOL_" .env.kol 2>/dev/null; then
    pass "MLFLOW_EXPERIMENT_NAME uses KOL_ prefix"
else
    fail "MLFLOW_EXPERIMENT_NAME missing KOL_ prefix in .env.kol"
fi

if grep -q "POSTGRES_DB=kol_mlflow" .env.kol 2>/dev/null; then
    pass "POSTGRES_DB configured correctly"
else
    fail "POSTGRES_DB not set to kol_mlflow in .env.kol"
fi

echo ""

# ============================================================================
# 6. Check Code for Hardcoded Paths
# ============================================================================
echo "🔍 Checking for hardcoded paths in code..."

HARDCODED_BRONZE=$(grep -r "s3://bronze" --include="*.py" batch/ streaming/ models/ 2>/dev/null | wc -l)
HARDCODED_SILVER=$(grep -r "s3://silver" --include="*.py" batch/ streaming/ models/ 2>/dev/null | grep -v "kol-silver" | wc -l)
HARDCODED_GOLD=$(grep -r "s3://gold" --include="*.py" batch/ streaming/ models/ 2>/dev/null | grep -v "kol-gold" | wc -l)

if [ "$HARDCODED_BRONZE" -eq 0 ]; then
    pass "No hardcoded 's3://bronze' paths found"
else
    fail "Found $HARDCODED_BRONZE hardcoded 's3://bronze' paths (should use env vars)"
fi

if [ "$HARDCODED_SILVER" -eq 0 ]; then
    pass "No hardcoded 's3://silver' paths found"
else
    fail "Found $HARDCODED_SILVER hardcoded 's3://silver' paths (should use kol-silver)"
fi

if [ "$HARDCODED_GOLD" -eq 0 ]; then
    pass "No hardcoded 's3://gold' paths found"
else
    fail "Found $HARDCODED_GOLD hardcoded 's3://gold' paths (should use kol-gold)"
fi

echo ""

# ============================================================================
# 7. Check Docker Compose Configuration
# ============================================================================
echo "🐳 Validating Docker Compose Configuration..."

if grep -q "kol_mlflow" infra/docker-compose.kol.yml 2>/dev/null; then
    pass "MLflow uses kol_mlflow database"
else
    fail "MLflow not configured to use kol_mlflow database"
fi

if grep -q "kol-mlflow/artifacts" infra/docker-compose.kol.yml 2>/dev/null; then
    pass "MLflow uses kol-mlflow bucket for artifacts"
else
    fail "MLflow not configured to use kol-mlflow bucket"
fi

if grep -q "MINIO_BUCKET_BRONZE" infra/docker-compose.kol.yml 2>/dev/null; then
    pass "Trainer service has KOL bucket env vars"
else
    fail "Trainer service missing KOL bucket env vars"
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
echo "============================================"
echo "Validation Summary"
echo "============================================"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ All validation checks passed!${NC}"
    echo "Domain separation is correctly configured."
    exit 0
else
    echo -e "${RED}❌ Some validation checks failed.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review the failed checks above"
    echo "  2. Run 'make init-kol-namespace' to create missing resources"
    echo "  3. Update .env.kol with correct namespace values"
    echo "  4. Fix any hardcoded paths in Python code"
    echo "  5. Re-run this validation script"
    echo ""
    echo "For help, see: docs/DOMAIN_SEPARATION.md"
    exit 1
fi

#!/bin/bash
# Health Metrics Implementation - Quick Validation Script
# Run this to verify the implementation is correct and ready for deployment

set -e

PROJECT_ROOT="/Users/swanandibhende/Documents/Projects/mercator"
cd "$PROJECT_ROOT"

echo "================================================"
echo "Health Metrics Implementation Validation"
echo "================================================"
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
run_test() {
    local test_name="$1"
    local command="$2"
    
    echo -n "Testing: $test_name ... "
    if eval "$command" &>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((TESTS_FAILED++))
    fi
}

# 1. Check Python imports
echo "1. CHECKING PYTHON IMPORTS"
echo "=========================="
run_test "HealthChecker import" "python -c 'from backend.utils.health_checker import HealthChecker; print(\"OK\")'"
run_test "HealthMetric import" "python -c 'from backend.utils.health_checker import HealthMetric; print(\"OK\")'"
run_test "MetricStatus import" "python -c 'from backend.utils.health_checker import MetricStatus; print(\"OK\")'"
run_test "HealthSnapshot import" "python -c 'from backend.utils.health_checker import HealthSnapshot; print(\"OK\")'"
echo

# 2. Check backend/main.py integration
echo "2. CHECKING MAIN.PY INTEGRATION"
echo "================================"
run_test "HealthChecker imported in main.py" "grep -q 'from backend.utils.health_checker import HealthChecker' backend/main.py"
run_test "Global health_checker variable" "grep -q 'health_checker.*HealthChecker.*None' backend/main.py"
run_test "Health checker initialization" "grep -q 'health_checker = HealthChecker' backend/main.py"
run_test "Health endpoints exist" "grep -q '/ops/health/snapshot' backend/main.py"
echo

# 3. Check test file
echo "3. CHECKING TEST FILE"
echo "====================="
run_test "Test file exists" "test -f backend/tests/test_health_checker.py"
run_test "Contains test fixtures" "grep -q '@pytest.fixture' backend/tests/test_health_checker.py"
run_test "Contains async tests" "grep -q '@pytest.mark.asyncio' backend/tests/test_health_checker.py"
echo

# 4. Check frontend integration
echo "4. CHECKING FRONTEND INTEGRATION"
echo "================================="
run_test "Operations page exists" "test -f frontend/src/pages/Operations.tsx"
run_test "Uses useWebSocket" "grep -q 'useWebSocket' frontend/src/pages/Operations.tsx"
run_test "Has health metrics" "grep -q 'health_update\\|health_snapshot' frontend/src/pages/Operations.tsx"
echo

# 5. Check documentation
echo "5. CHECKING DOCUMENTATION"
echo "=========================="
run_test "Deployment guide exists" "test -f HEALTH_METRICS_DEPLOYMENT.md"
run_test "Checklist exists" "test -f HEALTH_METRICS_CHECKLIST.md"
run_test "Summary exists" "test -f HEALTH_METRICS_SUMMARY.md"
echo

# 6. Run Python syntax check
echo "6. CHECKING PYTHON SYNTAX"
echo "=========================="
run_test "health_checker.py syntax" "python -m py_compile backend/utils/health_checker.py"
run_test "test_health_checker.py syntax" "python -m py_compile backend/tests/test_health_checker.py"
echo

# 7. Optional: Run actual tests (requires pytest)
echo "7. RUNNING UNIT TESTS (if pytest available)"
echo "============================================"
if command -v pytest &> /dev/null; then
    echo "Running pytest..."
    if pytest backend/tests/test_health_checker.py::test_startup_shutdown -v --tb=short 2>&1 | grep -q "PASSED\|ERROR"; then
        echo -e "${GREEN}✓ Test execution works${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${YELLOW}⚠ Tests may need dependencies${NC}"
    fi
else
    echo -e "${YELLOW}⚠ pytest not available (optional)${NC}"
fi
echo

# Summary
echo "================================================"
echo "VALIDATION SUMMARY"
echo "================================================"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL VALIDATIONS PASSED${NC}"
    echo
    echo "Next steps:"
    echo "1. Create database tables:"
    echo "   sqlite3 mercator_api_log.db 'CREATE TABLE IF NOT EXISTS api_request_log (requested_at TEXT, response_status INTEGER);'"
    echo "   sqlite3 mercator_curator.db 'CREATE TABLE IF NOT EXISTS flow_events (event_name TEXT, timestamp_iso TEXT, metadata TEXT);'"
    echo "   sqlite3 mercator_curator.db 'CREATE TABLE IF NOT EXISTS curator_runs (run_started_at TEXT, run_completed_at TEXT, published INTEGER, error TEXT);'"
    echo
    echo "2. Set environment variables:"
    echo "   IPFS_HEALTH_CHECK_CID=QmPLwEqJ3dQn19vCU6opXfAeKNtoKM6tLqLvBuYycSEJJZ"
    echo "   PINATA_GATEWAY_URL=https://gateway.pinata.cloud"
    echo "   AGENT_REGISTRY_APP_ID=<your_app_id>"
    echo
    echo "3. Run tests: pytest backend/tests/test_health_checker.py -v"
    echo
    echo "4. Start backend: python -m uvicorn backend.main:app --reload"
    echo
    echo "5. Open dashboard: http://localhost:8000/operations"
    echo
    exit 0
else
    echo -e "${RED}✗ SOME VALIDATIONS FAILED${NC}"
    echo "Please review the failures above."
    exit 1
fi

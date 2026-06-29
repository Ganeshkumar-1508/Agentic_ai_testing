#!/bin/bash
# TestAI — Health Check Script
# Verifies all services are running and responsive.
# Usage: bash scripts/health-check.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
  local name=$1
  local url=$2
  local status_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")

  if [ "$status_code" = "000" ]; then
    echo -e "${RED}FAIL${NC} $name — not reachable ($url)"
    return 1
  elif [ "$status_code" -ge 200 ] && [ "$status_code" -lt 400 ]; then
    echo -e "${GREEN}OK${NC}   $name — HTTP $status_code"
    return 0
  else
    echo -e "${YELLOW}WARN${NC} $name — HTTP $status_code"
    return 0
  fi
}

echo "========================================="
echo "  TestAI — Health Check"
echo "  $(date)"
echo "========================================="
echo ""

errors=0

check "Backend"        "http://localhost:8001/health"        || errors=$((errors + 1))
check "Frontend"       "http://localhost:3001/chat"           || errors=$((errors + 1))
check "OpenAPI Docs"   "http://localhost:8001/openapi.json"   || errors=$((errors + 1))
check "Swagger UI"     "http://localhost:8001/docs"           || errors=$((errors + 1))
check "Pipeline Runs"  "http://localhost:8001/runs"           || errors=$((errors + 1))
check "Sessions"       "http://localhost:8001/sessions"       || errors=$((errors + 1))
check "Dashboard Stats""http://localhost:8001/dashboard/stats" || errors=$((errors + 1))

echo ""
if [ "$errors" -gt 0 ]; then
  echo -e "${YELLOW}$errors service(s) have issues${NC}"
  exit 1
else
  echo -e "${GREEN}All services healthy${NC}"
  exit 0
fi

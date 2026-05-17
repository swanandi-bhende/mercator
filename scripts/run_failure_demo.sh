#!/usr/bin/env bash
set -euo pipefail

# Usage: ADMIN_KEY=yourkey ./scripts/run_failure_demo.sh
# Sends each known scenario to /admin/simulate_failure and saves a report.

API_URL=${API_URL:-http://localhost:8000}
ADMIN_KEY=${ADMIN_KEY:-}
REPORT_DIR=testnet-evidence/round3/error_scenarios
REPORT_FILE="$REPORT_DIR/failure_demo_report.json"

mkdir -p "$REPORT_DIR"

if [ -z "$ADMIN_KEY" ]; then
  echo "Provide ADMIN_KEY env var (ADMIN_KEY=...) to authenticate to /admin/simulate_failure"
  exit 1
fi

SCENARIOS=(
  ipfs_down
  algorand_timeout
  gemini_rate_limit
  insufficient_balance
  listing_expired
  unregistered_agent
  malformed_json
  payment_rejected
  reputation_too_low
  subscription_expired
  database_error
  x402_rejected
)

echo "[" > "$REPORT_FILE"
first=true
for s in "${SCENARIOS[@]}"; do
  echo "Triggering scenario: $s"
  resp=$(curl -s -X POST "$API_URL/admin/simulate_failure" -H "Content-Type: application/json" -H "x-admin-key: $ADMIN_KEY" -d "{\"scenario\": \"$s\", \"duration\": 12}") || resp="{\"success\":false,\"error\":\"curl_failed\"}"
  # Append comma-separated JSON objects
  if [ "$first" = true ]; then
    first=false
  else
    echo "," >> "$REPORT_FILE"
  fi
  echo "{\"scenario\": \"$s\", \"response\": $resp, \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" }" >> "$REPORT_FILE"
  # Wait a bit between scenarios so effects are observed
  sleep 15
done
echo "]" >> "$REPORT_FILE"

echo "Demo run complete — report at $REPORT_FILE"
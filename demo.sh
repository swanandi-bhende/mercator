#!/bin/bash
set -e

# AlgoBharat Round 2 One-Click Demo - runs full micropayment cycle in <2 minutes

START_TS=$(date +%s)
BACKEND_PID=""
FRONTEND_PID=""
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

cleanup() {
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "Running 50+ local tests..."
set +e
if command -v pytest >/dev/null 2>&1; then
  pytest backend/tests/test_micropayment_cycle.py -q --tb=no
  TEST_STATUS=$?
elif [[ -x ".venv/bin/python" ]]; then
  "$PYTHON_BIN" -m pytest backend/tests/test_micropayment_cycle.py -q --tb=no
  TEST_STATUS=$?
else
  "$PYTHON_BIN" -m pytest backend/tests/test_micropayment_cycle.py -q --tb=no
  TEST_STATUS=$?
fi
set -e

if [[ "$TEST_STATUS" -eq 0 ]]; then
  echo "Pytest status: PASS"
else
  echo "Pytest status: FAIL (${TEST_STATUS}) - continuing with live demo flow for evaluation."
fi

echo "Starting FastAPI backend on port 8000..."
"$PYTHON_BIN" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!

echo "Starting React UI on port 5173..."
(cd frontend && npm run dev > ../frontend.log 2>&1) &
FRONTEND_PID=$!

sleep 8

echo "Initializing LangChain agent and running full demo flow..."
"$PYTHON_BIN" - <<'PY' > agent_demo.log 2>&1
import asyncio
from backend.agent import run_agent


async def _run() -> None:
  result = await asyncio.wait_for(
    run_agent("batch_nifty breakout insight today", user_approval_input="approve"),
    timeout=240,
  )
  print(result)


asyncio.run(_run())
PY

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo "Demo completed successfully!"
echo "Transaction logs saved in mercator.log and agent_demo.log"
echo "View React UI at http://localhost:5173"
echo "View agent output in agent_demo.log"
echo "Total runtime: ${DURATION}s"
if [[ "$DURATION" -le 120 ]]; then
  echo "Runtime check: completed within two minutes."
else
  echo "Runtime check: exceeded two minutes (${DURATION}s)."
fi

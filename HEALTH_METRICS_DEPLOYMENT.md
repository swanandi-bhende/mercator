# Health Metrics & Operations Dashboard - Deployment Guide

## Overview

This guide covers the complete health metrics system implementation with 12 metrics across 5 categories, real-time WebSocket broadcasting, comprehensive testing, and the Operations dashboard.

## What Was Implemented

### Backend (backend/utils/health_checker.py)

**12 Health Metrics:**
1. **Algorand Network (3)**
   - `algorand_block_height`: Current round + latency measurement
   - `algorand_node_sync`: Sync status (synced vs catching up)
   - `algorand_pending_txns`: Mempool transaction count

2. **Smart Contracts (1 composite)**
   - `contract_states`: All 5 contracts (InsightListing, Escrow, FeeConfig, AgentRegistry, SubscriptionManager)
     - Tracks: app_id, is_paused, last_call_round, rounds_since_last_call
     - Status: GREEN <500 rounds, YELLOW 500-2000 rounds, RED >2000 or paused

3. **IPFS (1)**
   - `ipfs_gateway`: Gateway latency + test CID fetch (GREEN <2000ms, YELLOW 2000-5000ms, RED >5000ms)

4. **Backend (3)**
   - `api_endpoint_latencies`: 4 endpoints concurrently (GREEN <200ms, YELLOW 200-500ms, RED >500ms)
   - `websocket_connections`: Active connection count (informational, never fails)
   - `error_rate_last_5min`: API error percentage from api_request_log table

5. **Business (2)**
   - `usdc_volume_today`: Daily USDC micropayments from flow_events (informational)
   - `curator_agent_health`: Last run time + success status (35/70 min thresholds)

**Key Features:**
- Single reusable httpx.AsyncClient with configured timeouts
- All checks run concurrently via asyncio.gather(return_exceptions=True)
- 60-entry rolling window of snapshots (10 minutes at 10-second intervals)
- Status change detection and WebSocket broadcasting
- Comprehensive threshold management in HEALTH_THRESHOLDS dict

### Frontend (frontend/src/pages/Operations.tsx)

**Dashboard Sections:**
1. Overall Health banner (full-width, color-coded)
2. Algorand Network (3 metric cards)
3. Smart Contracts (5 contract cards)
4. Infrastructure (IPFS gauge, endpoint latency bar chart, error rate percentage)
5. Business Metrics (USDC volume, curator agent countdown, WS connections)
6. System Events Timeline (last 20 status changes)

**Features:**
- Real-time updates via WebSocket health_update events
- Refresh Now button for manual out-of-cycle checks
- Curator agent countdown timer (setInterval 1000ms)
- System alert banner for DOWN metrics
- Status color coding (green/yellow/red/gray)

### Testing (backend/tests/test_health_checker.py)

**14 Comprehensive Tests:**
- Startup/shutdown lifecycle
- Individual metric health/degraded/down states
- Exception handling without crashing health checks
- Status change detection and broadcasting
- Rolling window history limits
- Database query validation
- Informational metric behavior

## Pre-Deployment Checklist

### 1. Database Schema

Ensure these tables exist in your SQLite databases:

**api_request_log** (mercator_api_log.db):
```sql
CREATE TABLE api_request_log (
    requested_at TEXT,
    response_status INTEGER
);
```

**flow_events** (mercator_curator.db):
```sql
CREATE TABLE flow_events (
    event_name TEXT,
    timestamp_iso TEXT,
    metadata TEXT  -- JSON with amount_usdc
);
```

**curator_runs** (mercator_curator.db):
```sql
CREATE TABLE curator_runs (
    run_started_at TEXT,
    run_completed_at TEXT,
    published INTEGER,  -- 1 for success, 0 for failed
    error TEXT  -- Error message if failed
);
```

### 2. Environment Variables

Add these to your .env or Railway/Render environment:

```bash
# Health Check Configuration
IPFS_HEALTH_CHECK_CID=QmPLwEqJ3dQn19vCU6opXfAeKNtoKM6tLqLvBuYycSEJJZ  # Replace with your test CID
PINATA_GATEWAY_URL=https://gateway.pinata.cloud
API_LOG_DB=mercator_api_log.db
CURATOR_DB=mercator_curator.db

# Existing Algorand Configuration (should already be set)
INSIGHT_LISTING_APP_ID=758025190
REPUTATION_APP_ID=758022459
ESCROW_APP_ID=761839258
FEE_CONFIG_APP_ID=761839101
SUBSCRIPTION_MANAGER_APP_ID=761863755
AGENT_REGISTRY_APP_ID=<your_app_id>
```

### 3. APScheduler Configuration

The health_checker integration in main.py already configures APScheduler:
```python
scheduler.add_job(
    health_checker.run_all_checks,
    'interval',
    seconds=10,
    id='health_check',
    executor='asyncio',  # CRITICAL: Use asyncio executor
    replace_existing=True,
)
```

**Critical:** Always use `executor='asyncio'` for async health check functions to prevent event loop conflicts.

## Deployment Steps

### 1. Backend Deployment

```bash
# Ensure all packages are installed
pip install -r backend/requirements.txt

# Run tests locally
pytest backend/tests/test_health_checker.py -v

# Deploy to staging (Render, Railway, etc.)
# The health_checker will initialize automatically on app startup
```

### 2. Frontend Deployment

```bash
# Build frontend
cd frontend
npm run build

# Deploy to Vercel or staging environment
# The Operations dashboard will be available at /operations
```

### 3. Monitor Initial Deployment

After deployment:
1. Wait 10 seconds for first health check
2. Visit `/operations` page in browser
3. All 12 metrics should populate with live data
4. WebSocket connection should show "active connections" updating in real-time
5. Check backend logs for any health_checker initialization errors

## Testing on Staging

### Test 1: Verify All Metrics Populate

1. Open Operations dashboard
2. Wait 30 seconds (allows 3 health check cycles)
3. Verify all sections show data:
   - ✓ Algorand Network: block_height, sync status, pending txns
   - ✓ Contracts: all 5 apps showing app_id, pause status, rounds_since_call
   - ✓ IPFS: latency and success flag
   - ✓ Backend: endpoint latencies for 4 endpoints
   - ✓ Business: USDC volume, curator status, WS connections

### Test 2: Status Change Detection

1. Take note of initial overall_status (should be "healthy")
2. Temporarily break one health check:
   ```bash
   # In Railway/Render, temporarily set IPFS_GATEWAY_URL to invalid URL
   IPFS_GATEWAY_URL=https://invalid.example.com
   ```
3. Wait 10 seconds for next health check
4. Verify:
   - ✓ IPFS metric turns red (status: down)
   - ✓ Overall status changes to "down"
   - ✓ Alert count increases to 1
   - ✓ System alert banner appears at top of page with message about IPFS being down
5. Fix the URL
6. Verify metrics return to green within 10 seconds

### Test 3: Alert Banner on Home Page

1. Leave IPFS_GATEWAY_URL broken (from Test 2)
2. Navigate to Home page (should not be Operations page)
3. Verify:
   - ✓ Alert banner appears at very top of page (above navigation)
   - ✓ Message reads: "⚠️ System Alert: 1 system component(s) are down — ipfs_gateway"
   - ✓ Banner is dismissible with X button
4. Fix IPFS URL
5. Verify banner disappears within 10 seconds OR new health_update event shows no alerts

### Test 4: Refresh Now Button

1. Click "Refresh Now" button on Operations dashboard
2. Verify:
   - ✓ New health check is triggered immediately (doesn't wait 10s)
   - ✓ Timestamp updates
   - ✓ Metrics reflect current state

### Test 5: Curator Agent Countdown

1. Look at "Curator Agent" card in Business Metrics section
2. Verify:
   - ✓ "Last Run" shows a timestamp
   - ✓ "Success" shows either "Success" (green) or "Failed" (red)
   - ✓ "Next run in: X seconds" countdown decrements every second

### Test 6: WebSocket Connection Tracking

1. Open multiple browser tabs to same application
2. Each tab should connect as a WebSocket client
3. Verify:
   - ✓ "Active Connections" card shows increasing count
   - ✓ Closing tabs decreases the count

### Test 7: Error Rate Calculation

1. Trigger some API errors:
   ```bash
   # Make requests to invalid endpoints to generate 400/500 errors
   curl http://localhost:8000/invalid-endpoint
   ```
2. Wait 5 minutes for errors to be logged
3. Verify error_rate_last_5min metric shows:
   - ✓ Correct error percentage
   - ✓ Color changes: GREEN <5%, YELLOW 5-15%, RED >15%

## Monitoring in Production

### Health Check Dashboard URL
```
https://your-deployment.com/operations
```

### Health Check Endpoints

```bash
# Get latest snapshot
curl https://your-deployment.com/ops/health/snapshot

# Get last 10 minutes of history (60 snapshots)
curl https://your-deployment.com/ops/health/history?minutes=10

# Trigger manual refresh
curl -X POST https://your-deployment.com/admin/health/refresh
```

### Logs to Monitor

```bash
# Health checker initialization
"Health checker initialized and started"
"Health checker job scheduled every 10 seconds"

# Status changes
# Each status change will be logged via broadcast to WebSocket

# Errors
"Failed to check <metric_name>: <error>"
"Failed to broadcast <event_type>: <error>"
```

## Troubleshooting

### Issue: Health metrics not populating

**Symptoms:** Dashboard shows "No data" or metrics are UNKNOWN

**Solutions:**
1. Check APScheduler is running: `scheduler.running` should be True in logs
2. Verify health_checker initialized: Look for "Health checker initialized" in logs
3. Check database paths are correct and files exist
4. Verify environment variables are set (especially app IDs)
5. Check algod_client and indexer_client are initialized correctly

### Issue: Alert banner not appearing on Home page

**Symptoms:** Operations dashboard shows alerts but Home page doesn't

**Solutions:**
1. Verify WebSocket connection is active (check browser console)
2. Check that ws_manager.broadcast("system_alert", ...) is being called
3. Verify Home page component is listening for "system_alert" events
4. Check alert_id tracking prevents duplicate alerts

### Issue: Curator agent health showing UNKNOWN

**Symptoms:** "Curator Agent has not run yet since server startup"

**Solutions:**
1. Verify curator_runs table has at least one row
2. Verify columns match: run_completed_at, published, error
3. Ensure curator_agent.run_full_cycle is scheduled and running
4. Check curator database path in environment variable

### Issue: IPFS health check always DOWN

**Symptoms:** IPFS metric is always RED even with correct gateway

**Solutions:**
1. Verify IPFS_HEALTH_CHECK_CID environment variable is set
2. Confirm the CID exists on the gateway: `curl https://gateway.pinata.cloud/ipfs/{CID}`
3. Check test file contains "mercator" substring (case-insensitive)
4. Verify PINATA_GATEWAY_URL is correct and accessible
5. Check httpx.AsyncClient timeout isn't too aggressive (currently 3s read timeout)

### Issue: Scheduler crashes with "event loop conflict"

**Symptoms:** RuntimeError about asyncio event loop in logs

**Solutions:**
1. **CRITICAL:** Verify `executor='asyncio'` is set for health_check job
2. Ensure health_checker methods are all `async def` (never use asyncio.run inside)
3. Check no other jobs use the health_checker without the asyncio executor

## Performance Metrics

### Expected Resource Usage

**CPU:**
- ~2-5% per health check cycle (all 10 checks concurrent)
- 10 second interval = low continuous load

**Memory:**
- HealthChecker instance: ~5-10MB
- Snapshot history (60 entries): ~2-5MB per entry (depends on metric complexity)
- Total: ~30-50MB for full history window

**Network:**
- ~10-20 HTTP requests per 10-second cycle (distributed across checks)
- WebSocket broadcasts: 1-2 per cycle (only on changes)
- Database queries: 5-6 per cycle (SQLite local)

**Recommended Settings:**
- APScheduler thread pool: default (10 threads)
- httpx connection pool: 10 (set in health_checker.startup())
- Snapshot history: 60 entries (10 minutes)
- Health check interval: 10 seconds

## Rollback Plan

If health metrics cause issues:

1. **Disable health checks:** Comment out scheduler.add_job() in main.py
2. **Disable endpoints:** Remove /ops/health/* route handlers
3. **Shutdown gracefully:** Call health_checker.shutdown() in lifespan

The system is designed to be non-blocking:
- Failures in individual health checks don't crash the system
- WebSocket broadcasts are best-effort (non-blocking)
- Health checker runs in background (doesn't block FastAPI routes)

## Questions?

Refer to:
- [backend/utils/health_checker.py](../backend/utils/health_checker.py) - Full implementation with docstrings
- [backend/tests/test_health_checker.py](../backend/tests/test_health_checker.py) - Test examples
- [frontend/src/pages/Operations.tsx](../frontend/src/pages/Operations.tsx) - Dashboard component

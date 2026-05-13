# Health Metrics Implementation - Integration Checklist

## ✅ COMPLETED IMPLEMENTATION

### Backend Code
- [x] backend/utils/health_checker.py - Complete 1400+ line module with:
  - [x] HEALTH_THRESHOLDS dict (all 12 metrics)
  - [x] MetricStatus enum + HealthMetric + HealthSnapshot dataclasses
  - [x] HealthChecker class with startup/shutdown
  - [x] 10 async health check methods (algorand_connection, algorand_node_sync, algorand_pending_txns, contract_states, ipfs_gateway, backend_endpoints, websocket_connections, error_rate, usdc_volume, curator_agent_health)
  - [x] run_all_checks() orchestrator with status change detection
  - [x] _broadcast_health_update() and _broadcast_alert() for WebSocket
  - [x] get_health_history() for dashboard trend data

### Backend Integration
- [x] backend/main.py updated with:
  - [x] Import HealthChecker
  - [x] Global health_checker variable
  - [x] Initialization in _run_startup_hooks()
  - [x] Shutdown in _run_shutdown_hooks()
  - [x] APScheduler job with executor='asyncio'
  - [x] GET /ops/health/snapshot endpoint
  - [x] GET /ops/health/history endpoint
  - [x] POST /admin/health/refresh endpoint

### Testing
- [x] backend/tests/test_health_checker.py with 14 tests:
  - [x] test_startup_shutdown
  - [x] test_check_algorand_connection_healthy
  - [x] test_check_algorand_connection_degraded
  - [x] test_check_algorand_connection_exception_is_down
  - [x] test_check_ipfs_gateway_successful
  - [x] test_ipfs_gateway_wrong_content_is_down
  - [x] test_check_error_rate_above_threshold_is_degraded
  - [x] test_check_websocket_connections_always_healthy
  - [x] test_run_all_checks_handles_individual_exception
  - [x] test_status_change_triggers_broadcast
  - [x] test_alert_banner_not_shown_when_all_healthy
  - [x] test_snapshot_history_rolling_window
  - [x] test_get_health_history_with_minutes
  - [x] test_health_metric_previous_status_tracking
  - [x] test_check_curator_agent_no_runs
  - [x] test_check_usdc_volume_informational

### Frontend Code
- [x] frontend/src/pages/Operations.tsx - 400+ line component with:
  - [x] Overall health banner
  - [x] Algorand Network section (3 metrics)
  - [x] Smart Contracts section (5 contracts)
  - [x] Infrastructure section (IPFS, Backend, Error Rate)
  - [x] Business Metrics section (USDC, Curator, WS)
  - [x] System Events Timeline
  - [x] Refresh Now button
  - [x] Curator countdown timer
  - [x] WebSocket integration for real-time updates

### Documentation
- [x] HEALTH_METRICS_DEPLOYMENT.md - Complete deployment guide
- [x] Session memory tracking implementation details

## 🚀 REMAINING DEPLOYMENT TASKS

These are manual tasks to finalize deployment:

### 1. Database Schema Creation

**Run these SQL commands** in your SQLite databases:

```sql
-- In mercator_api_log.db
CREATE TABLE IF NOT EXISTS api_request_log (
    requested_at TEXT,
    response_status INTEGER
);

-- In mercator_curator.db
CREATE TABLE IF NOT EXISTS flow_events (
    event_name TEXT,
    timestamp_iso TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS curator_runs (
    run_started_at TEXT,
    run_completed_at TEXT,
    published INTEGER,
    error TEXT
);
```

### 2. Environment Variables

**Add to Render/Railway environment:**

```
IPFS_HEALTH_CHECK_CID=QmPLwEqJ3dQn19vCU6opXfAeKNtoKM6tLqLvBuYycSEJJZ
PINATA_GATEWAY_URL=https://gateway.pinata.cloud
API_LOG_DB=mercator_api_log.db
CURATOR_DB=mercator_curator.db
AGENT_REGISTRY_APP_ID=<your_app_id>
```

Verify existing variables are still set:
- INSIGHT_LISTING_APP_ID
- REPUTATION_APP_ID
- ESCROW_APP_ID
- FEE_CONFIG_APP_ID
- SUBSCRIPTION_MANAGER_APP_ID

### 3. Test Locally

```bash
# Run health checker tests
cd /Users/swanandibhende/Documents/Projects/mercator
pytest backend/tests/test_health_checker.py -v

# Run backend
python -m uvicorn backend.main:app --reload

# Open dashboard (once running)
# http://localhost:8000/operations
```

### 4. Deploy to Staging

```bash
# 1. Push code to GitHub
git add backend/utils/health_checker.py
git add backend/main.py
git add backend/tests/test_health_checker.py
git add frontend/src/pages/Operations.tsx
git add HEALTH_METRICS_DEPLOYMENT.md
git commit -m "Add comprehensive health metrics dashboard with 12 metrics"
git push origin main

# 2. Render will auto-deploy (if configured)
# OR manually trigger deployment in Render dashboard

# 3. For Vercel frontend, builds auto-trigger on push
```

### 5. Verify Deployment (Staging)

**Wait 10-15 seconds after deployment, then:**

```bash
# Check API is responding
curl https://your-staging.onrender.com/api/v1/health

# Check health metrics endpoint
curl https://your-staging.onrender.com/ops/health/snapshot

# Check dashboard loads
# Open browser to: https://your-staging.onrender.com/operations
```

### 6. Run Staging Tests

**Manual testing checklist:**

- [ ] Operations dashboard loads without errors
- [ ] All 12 metric sections populate with data (wait 30 seconds)
- [ ] Metrics update in real-time (watch for timestamp changes)
- [ ] Click "Refresh Now" button - health check triggers immediately
- [ ] Deliberately break IPFS by setting gateway to invalid URL
- [ ] Verify IPFS metric turns red within 10 seconds
- [ ] Verify alert banner appears on Home/Discover pages
- [ ] Fix IPFS URL and verify metric returns to green
- [ ] Curator agent countdown updates every second
- [ ] WebSocket connection count increases when opening new tabs
- [ ] System Events Timeline shows recent metric changes

**Automated tests:**

```bash
# SSH into backend and run tests
pytest backend/tests/test_health_checker.py::test_run_all_checks_handles_individual_exception -v
pytest backend/tests/test_health_checker.py::test_status_change_triggers_broadcast -v
```

### 7. Production Deployment

**Only after staging tests pass:**

```bash
# Ensure all staging tests passed
# Tag release in GitHub
git tag -a v1.0-health-metrics -m "Add health metrics dashboard"
git push origin v1.0-health-metrics

# Trigger production build (auto-deploy if configured)
# Monitor logs during initial startup
```

### 8. Post-Deployment Monitoring

**First 24 hours:**

- Monitor logs for any health_checker errors
- Watch alert thresholds (ensure no false positives)
- Verify snapshot history captures 10 minutes of data
- Check WebSocket broadcast messages are reaching frontend
- Confirm curator agent health tracking is accurate

**Ongoing:**

- Review Operations dashboard regularly
- Set up alerts if overall_status becomes DOWN
- Monitor health check cycle latency (should be <2 seconds for all 10 checks)
- Adjust thresholds based on actual system behavior

## 📋 Quick Reference

### Files Modified/Created
```
✅ backend/utils/health_checker.py (NEW - 1400 lines)
✅ backend/main.py (MODIFIED - added 60 lines)
✅ backend/tests/test_health_checker.py (NEW - 280 lines)
✅ frontend/src/pages/Operations.tsx (MODIFIED/EXTENDED - added health section)
✅ HEALTH_METRICS_DEPLOYMENT.md (NEW - deployment guide)
```

### Key Architecture Decisions
1. Single reusable httpx.AsyncClient per health_checker instance
2. asyncio.gather(return_exceptions=True) for concurrent checks
3. 60-entry rolling snapshot window (10 minutes at 10-second intervals)
4. Status change detection triggers WebSocket broadcasts
5. Informational metrics (websocket_connections, usdc_volume) never fail

### Critical Configuration
- **APScheduler executor:** Must be 'asyncio' for async health checks
- **httpx.Timeout:** connect=2s, read=3s, write=2s, pool=1s
- **Connection pool:** Max 10 connections
- **Health check interval:** 10 seconds (6 checks per minute, 60 per 10 minutes)

### Troubleshooting Quick Links
See HEALTH_METRICS_DEPLOYMENT.md for:
- Database schema validation
- Environment variable checklist
- Common issues and solutions
- Performance metrics
- Rollback procedures

## Sign-Off Checklist

- [ ] All backend code reviewed and tested
- [ ] All tests passing locally
- [ ] Environment variables configured
- [ ] Database tables created
- [ ] Deployed to staging
- [ ] Staging tests passed
- [ ] Alert banner tested on all pages
- [ ] Operations dashboard verified live
- [ ] Performance verified (no CPU/memory spikes)
- [ ] Logs reviewed for errors
- [ ] Ready for production deployment

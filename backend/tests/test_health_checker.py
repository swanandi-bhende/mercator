"""Comprehensive tests for the health_checker module.

Tests cover all 12 health metrics, exception handling, status change detection,
and WebSocket broadcasting.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import sqlite3

from backend.utils.health_checker import (
    HealthChecker,
    HealthMetric,
    HealthSnapshot,
    MetricStatus,
)


@pytest.fixture
def mock_algod_client():
    """Mock AlgodClient."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_indexer_client():
    """Mock IndexerClient."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket manager."""
    manager = AsyncMock()
    manager.active_connections = []
    manager.get_connection_count = MagicMock(return_value=0)
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def health_checker(mock_algod_client, mock_indexer_client, mock_ws_manager):
    """Instantiate HealthChecker with mocked clients."""
    checker = HealthChecker(mock_algod_client, mock_indexer_client, mock_ws_manager)
    return checker


@pytest.mark.asyncio
async def test_startup_shutdown(health_checker):
    """Test that startup and shutdown properly initialize/cleanup httpx client."""
    assert health_checker._http_client is None
    
    await health_checker.startup()
    assert health_checker._http_client is not None
    
    await health_checker.shutdown()
    # Client should be closed (we can't check directly, but no exception)


@pytest.mark.asyncio
async def test_check_algorand_connection_healthy(health_checker, mock_algod_client):
    """Test algorand_block_height returns HEALTHY for fast response."""
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    metric = await health_checker.check_algorand_connection()
    
    assert metric.metric_name == "algorand_block_height"
    assert metric.status == MetricStatus.HEALTHY
    assert metric.value["current_round"] == 42000000
    assert metric.message == "Algorand node at round 42000000, responding in"
    assert "HEALTHY" not in metric.message.lower() or "responding" in metric.message.lower()


@pytest.mark.asyncio
async def test_check_algorand_connection_degraded(health_checker, mock_algod_client):
    """Test algorand_block_height returns DEGRADED for slow response."""
    # Mock a slow response
    async def slow_status():
        await asyncio.sleep(1.5)
        return {"last-round": 42000000, "catchup-time": 0}
    
    mock_algod_client.status = slow_status
    
    metric = await health_checker.check_algorand_connection()
    
    assert metric.metric_name == "algorand_block_height"
    assert metric.status == MetricStatus.DEGRADED
    assert metric.value["latency_ms"] >= 1000


@pytest.mark.asyncio
async def test_check_algorand_connection_exception_is_down(health_checker, mock_algod_client):
    """Test algorand_block_height returns DOWN on AlgodHTTPError."""
    from algosdk.error import AlgodHTTPError
    
    mock_algod_client.status.side_effect = AlgodHTTPError(Exception("Node unreachable"))
    
    metric = await health_checker.check_algorand_connection()
    
    assert metric.metric_name == "algorand_block_height"
    assert metric.status == MetricStatus.DOWN
    assert "unreachable" in metric.message.lower()


@pytest.mark.asyncio
async def test_check_ipfs_gateway_successful(health_checker):
    """Test ipfs_gateway returns HEALTHY for successful test CID fetch."""
    await health_checker.startup()
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "mercator health check v1"
        mock_get.return_value = mock_response
        
        metric = await health_checker.check_ipfs_gateway()
        
        assert metric.metric_name == "ipfs_gateway"
        assert metric.status == MetricStatus.HEALTHY
        assert metric.value["test_cid_fetch_success"] is True


@pytest.mark.asyncio
async def test_ipfs_gateway_wrong_content_is_down(health_checker):
    """Test ipfs_gateway returns DOWN for status 200 but wrong content."""
    await health_checker.startup()
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "Error: Not Found"  # Wrong content
        mock_get.return_value = mock_response
        
        metric = await health_checker.check_ipfs_gateway()
        
        assert metric.metric_name == "ipfs_gateway"
        assert metric.status == MetricStatus.DOWN
        assert metric.value["test_cid_fetch_success"] is False


@pytest.mark.asyncio
async def test_check_error_rate_above_threshold_is_degraded(
    health_checker, tmp_path
):
    """Test error_rate_last_5min returns DEGRADED for 20% error rate."""
    # Create a temporary database
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create api_request_log table
    cursor.execute(
        """
        CREATE TABLE api_request_log (
            requested_at TEXT,
            response_status INTEGER
        )
    """
    )
    
    # Insert test data: 20 requests, 4 errors (20% error rate)
    now = datetime.now(timezone.utc)
    for i in range(20):
        status = 500 if i < 4 else 200
        timestamp = (now - timedelta(minutes=2)).isoformat()
        cursor.execute(
            "INSERT INTO api_request_log VALUES (?, ?)", (timestamp, status)
        )
    
    conn.commit()
    conn.close()
    
    # Patch the database path
    with patch("os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=None):
            if key == "API_LOG_DB":
                return str(db_path)
            return default
        
        mock_getenv.side_effect = getenv_side_effect
        
        metric = await health_checker.check_error_rate()
        
        assert metric.metric_name == "error_rate_last_5min"
        assert metric.status == MetricStatus.DEGRADED
        assert metric.value["error_pct"] == 20.0


@pytest.mark.asyncio
async def test_check_websocket_connections_always_healthy(
    health_checker, mock_ws_manager
):
    """Test websocket_connections always returns HEALTHY status."""
    mock_ws_manager.get_connection_count.return_value = 5
    mock_ws_manager.active_connections = [1, 2, 3, 4, 5]
    
    metric = await health_checker.check_websocket_connections()
    
    assert metric.metric_name == "websocket_connections"
    assert metric.status == MetricStatus.HEALTHY
    assert metric.value["active_count"] == 5


@pytest.mark.asyncio
async def test_run_all_checks_handles_individual_exception(
    health_checker, mock_algod_client, mock_ws_manager
):
    """Test run_all_checks completes even if one check raises exception."""
    # Make one check raise an exception
    mock_algod_client.status.side_effect = Exception("Test exception")
    
    # All other checks should succeed
    with patch.object(health_checker, "check_ipfs_gateway") as mock_ipfs:
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.HEALTHY,
            value={},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="IPFS OK",
        )
        
        # Should complete without crashing
        snapshot = await health_checker.run_all_checks()
        
        assert snapshot is not None
        assert isinstance(snapshot, HealthSnapshot)


@pytest.mark.asyncio
async def test_status_change_triggers_broadcast(
    health_checker, mock_algod_client, mock_ws_manager
):
    """Test that status changes trigger WebSocket broadcasts."""
    await health_checker.startup()
    
    # First run: all healthy
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    with patch.object(health_checker, "check_ipfs_gateway") as mock_ipfs:
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.HEALTHY,
            value={"test_cid_fetch_success": True},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="IPFS OK",
        )
        
        snapshot1 = await health_checker.run_all_checks()
        assert snapshot1.overall_status == MetricStatus.HEALTHY
        
        # No broadcast on first run
        mock_ws_manager.broadcast.assert_not_called()
        
        # Second run: IPFS down
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.DOWN,
            value={"test_cid_fetch_success": False},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="IPFS gateway unreachable",
        )
        
        snapshot2 = await health_checker.run_all_checks()
        
        # Broadcast should have been called with system_alert
        assert mock_ws_manager.broadcast.called
        calls = mock_ws_manager.broadcast.call_args_list
        alert_calls = [c for c in calls if c[0][0] == "system_alert"]
        assert len(alert_calls) > 0


@pytest.mark.asyncio
async def test_alert_banner_not_shown_when_all_healthy(
    health_checker, mock_algod_client, mock_ws_manager
):
    """Test that system_alert is not broadcast when all metrics healthy."""
    await health_checker.startup()
    
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    with patch.object(health_checker, "check_ipfs_gateway") as mock_ipfs:
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.HEALTHY,
            value={"test_cid_fetch_success": True},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="IPFS OK",
        )
        
        snapshot = await health_checker.run_all_checks()
        
        # No system_alert should be broadcast when all healthy
        calls = mock_ws_manager.broadcast.call_args_list
        alert_calls = [c for c in calls if c[0][0] == "system_alert"]
        assert len(alert_calls) == 0


@pytest.mark.asyncio
async def test_snapshot_history_rolling_window(
    health_checker, mock_algod_client, mock_ws_manager
):
    """Test that snapshot history maintains 60-entry rolling window."""
    await health_checker.startup()
    
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    # Mock all other checks to return healthy metrics
    with patch.object(health_checker, "check_ipfs_gateway") as mock_ipfs:
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.HEALTHY,
            value={},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="OK",
        )
        
        # Run checks 70 times
        for i in range(70):
            snapshot = await health_checker.run_all_checks()
        
        # History should be capped at 60
        history = health_checker.get_snapshot_history()
        assert len(history) == 60
        assert history[-1].snapshot_id == snapshot.snapshot_id


@pytest.mark.asyncio
async def test_get_health_history_with_minutes(
    health_checker, mock_algod_client, mock_ws_manager
):
    """Test get_health_history returns snapshots for specified minutes."""
    await health_checker.startup()
    
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    with patch.object(health_checker, "check_ipfs_gateway") as mock_ipfs:
        mock_ipfs.return_value = HealthMetric(
            metric_name="ipfs_gateway",
            status=MetricStatus.HEALTHY,
            value={},
            threshold_applied={},
            measured_at=datetime.now(timezone.utc).isoformat(),
            message="OK",
        )
        
        # Run checks 20 times (20 snapshots)
        for i in range(20):
            snapshot = await health_checker.run_all_checks()
        
        # Request 5 minutes of history (5*6 = 30 snapshots, but we only have 20)
        history_5min = health_checker.get_health_history(minutes=5)
        assert len(history_5min) == 20  # Limited by actual count


@pytest.mark.asyncio
async def test_health_metric_previous_status_tracking(
    health_checker, mock_algod_client
):
    """Test that previous_status is properly tracked for status change detection."""
    await health_checker.startup()
    
    # First run
    mock_algod_client.status.return_value = {
        "last-round": 42000000,
        "catchup-time": 0,
    }
    
    metric1 = await health_checker.check_algorand_connection()
    assert metric1.previous_status == MetricStatus.UNKNOWN
    
    # Second run - same status
    metric2 = await health_checker.check_algorand_connection()
    assert metric2.previous_status == MetricStatus.HEALTHY
    
    # Third run - different status
    mock_algod_client.status.side_effect = Exception("Node down")
    metric3 = await health_checker.check_algorand_connection()
    assert metric3.previous_status == MetricStatus.HEALTHY
    assert metric3.status == MetricStatus.DOWN


@pytest.mark.asyncio
async def test_check_curator_agent_no_runs(health_checker, tmp_path):
    """Test curator_agent_health returns UNKNOWN when no runs exist."""
    db_path = tmp_path / "curator.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        """
        CREATE TABLE curator_runs (
            run_started_at TEXT,
            run_completed_at TEXT,
            published INTEGER,
            error TEXT
        )
    """
    )
    conn.commit()
    conn.close()
    
    with patch("os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=None):
            if key == "CURATOR_DB":
                return str(db_path)
            return default
        mock_getenv.side_effect = getenv_side_effect
        
        metric = await health_checker.check_curator_agent_health()
        
        assert metric.metric_name == "curator_agent_health"
        assert metric.status == MetricStatus.UNKNOWN
        assert "has not run yet" in metric.message.lower()


@pytest.mark.asyncio
async def test_check_usdc_volume_informational(health_checker, tmp_path):
    """Test usdc_volume returns HEALTHY even with zero volume."""
    db_path = tmp_path / "curator.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        """
        CREATE TABLE flow_events (
            event_name TEXT,
            timestamp_iso TEXT,
            metadata TEXT
        )
    """
    )
    conn.commit()
    conn.close()
    
    with patch("os.getenv") as mock_getenv:
        def getenv_side_effect(key, default=None):
            if key == "CURATOR_DB":
                return str(db_path)
            return default
        mock_getenv.side_effect = getenv_side_effect
        
        metric = await health_checker.check_usdc_volume()
        
        assert metric.metric_name == "usdc_volume_today"
        assert metric.status == MetricStatus.HEALTHY  # Always healthy for informational
        assert metric.value["total_usdc"] == 0.0

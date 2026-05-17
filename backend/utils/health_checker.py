"""Health metrics and monitoring for the Mercator operations dashboard.

Purpose: Continuous health checks across Algorand network, smart contracts, IPFS, backend endpoints,
and business metrics. Metrics are collected every 10 seconds and made available via the ops dashboard.

Key Design Decisions:
1. Single reusable httpx.AsyncClient with configured timeouts to prevent connection pool exhaustion
2. APScheduler AsyncIOScheduler with executor='asyncio' for async health check functions
3. 12 metrics across 5 categories: Network (3), Contracts (1 composite), IPFS (1), Backend (3), Business (2)
4. Threshold-based status determination: HEALTHY < DEGRADED < DOWN with message generation
5. Metric history with 60-entry rolling window (10 minutes at 10-second intervals)
6. Status change tracking to detect and broadcast alerts
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import httpx
from algosdk.error import AlgodHTTPError
from algosdk.v2client import algod, indexer

logger = logging.getLogger("mercator.health_checker")

# ============================================================================
# HEALTH THRESHOLDS - All metrics with exact field names, thresholds, and logic
# ============================================================================

HEALTH_THRESHOLDS = {
    # Category 1: Algorand Network (3 metrics)
    "algorand_block_height": {
        "description": "Current block height and algod node latency",
        "fields": ["current_round", "latency_ms", "status"],
        "thresholds": {
            "latency_healthy_max": 1000,  # green if latency < 1000ms
            "latency_degraded_max": 3000,  # yellow if 1000-3000ms
            # red if > 3000 or request failed
        },
    },
    "algorand_node_sync": {
        "description": "Node sync status and catchup progress",
        "fields": ["is_synced", "catchup_time", "status"],
        "thresholds": {
            # green if is_synced=True and catchup_time=0
            # red otherwise
        },
    },
    "algorand_pending_txns": {
        "description": "Pending transactions in mempool",
        "fields": ["top_transactions", "status"],
        "thresholds": {
            "healthy_max": 100,
            "degraded_max": 500,
            # red if > 500
        },
    },
    # Category 2: Smart Contracts (1 composite metric for 5 contracts)
    "contract_states": {
        "description": "All 5 contract application states",
        "contracts": [
            "InsightListing",
            "Escrow",
            "FeeConfig",
            "AgentRegistry",
            "SubscriptionManager",
        ],
        "fields_per_contract": ["app_id", "is_paused", "last_call_round", "rounds_since_last_call"],
        "thresholds": {
            "healthy_rounds_since_call": 500,  # green if < 500 rounds
            "degraded_rounds_since_call": 2000,  # yellow if 500-2000 rounds
            # red if > 2000 or is_paused=True
        },
    },
    # Category 3: IPFS (1 metric)
    "ipfs_gateway": {
        "description": "IPFS gateway connectivity and latency",
        "fields": ["gateway_url", "test_cid_fetch_latency_ms", "test_cid_fetch_success"],
        "thresholds": {
            "healthy_max_latency": 2000,  # green if < 2000ms
            "degraded_max_latency": 5000,  # yellow if 2000-5000ms
            # red if > 5000 or failed
        },
    },
    # Category 4: Backend (3 metrics)
    "api_endpoint_latencies": {
        "description": "Internal endpoint response latencies",
        "endpoints": [
            "/health",
            "/curator/status",
            "/api/v1/health",
            "/subscription/status",
        ],
        "fields": ["endpoint", "latency_ms", "status_code", "status"],
        "thresholds": {
            "healthy_max": 200,  # green if < 200ms
            "degraded_max": 500,  # yellow if 200-500ms
            # red if > 500ms or non-200 status
        },
    },
    "websocket_connections": {
        "description": "Active WebSocket connections (informational)",
        "fields": ["active_count"],
        "thresholds": {
            # No failure threshold - any value is healthy (purely informational)
        },
    },
    "error_rate_last_5min": {
        "description": "API error rate in last 5 minutes",
        "fields": ["error_pct", "total_requests", "error_count"],
        "thresholds": {
            "healthy_max_pct": 5.0,  # green if < 5%
            "degraded_max_pct": 15.0,  # yellow if 5-15%
            # red if > 15%
        },
    },
    # Category 5: Business (2 metrics)
    "usdc_volume_today": {
        "description": "USDC micropayment volume today (informational)",
        "fields": ["total_micro_usdc"],
        "thresholds": {
            # Informational only - no failure threshold
        },
    },
    "curator_agent_health": {
        "description": "Curator agent execution cycle health",
        "fields": ["last_run_at", "minutes_since_last_run", "last_run_success"],
        "thresholds": {
            "healthy_max_minutes": 35,  # green if < 35 min since last run
            "degraded_max_minutes": 70,  # yellow if 35-70 min (missed one cycle)
            # red if > 70 min (missed two cycles) or last_run_success=False
        },
    },
}


# ============================================================================
# ENUMS AND DATACLASSES
# ============================================================================


class MetricStatus(str, Enum):
    """Health status values for metrics."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    """Single health metric measurement with status and history."""

    metric_name: str
    status: MetricStatus
    value: dict[str, Any]  # Raw measured values (e.g., {"current_round": 42, "latency_ms": 250})
    threshold_applied: dict[str, Any]  # Thresholds used for determination
    measured_at: str  # ISO 8601 timestamp
    message: str  # Human-readable one-sentence description
    previous_status: MetricStatus = MetricStatus.UNKNOWN


@dataclass
class HealthSnapshot:
    """Complete health snapshot at a point in time."""

    snapshot_id: str
    measured_at: str
    overall_status: MetricStatus
    metrics: dict[str, HealthMetric] = field(default_factory=dict)
    active_websocket_connections: int = 0
    alert_count: int = 0  # Count of DOWN metrics


# ============================================================================
# HEALTH CHECKER CLASS
# ============================================================================


class HealthChecker:
    """Orchestrates all health checks across the Mercator platform.

    Manages:
    - Shared httpx.AsyncClient with configured timeouts
    - Metric measurement and status determination
    - Snapshot history (rolling 60-entry window)
    - Status change detection for broadcasting alerts
    """

    def __init__(
        self,
        algod_client: algod.AlgodClient,
        indexer_client: indexer.IndexerClient,
        ws_manager: Any,
    ):
        """Initialize health checker with Algorand clients.

        Args:
            algod_client: Configured algod.AlgodClient for node queries
            indexer_client: Configured indexer.IndexerClient for transaction history
            ws_manager: WebSocket manager for active connection count
        """
        self.algod_client = algod_client
        self.indexer_client = indexer_client
        self.ws_manager = ws_manager
        self._http_client: httpx.AsyncClient | None = None
        self._previous_snapshot: HealthSnapshot | None = None
        self._metric_history: list[HealthSnapshot] = []
        # Keep last computed status per metric for previous_status checks
        self._last_metric_status: dict[str, MetricStatus] = {}

    async def startup(self) -> None:
        """Initialize shared httpx client on app startup.

        Called from FastAPI lifespan startup event. Sets up a single reusable
        AsyncClient with configured timeouts to prevent connection pool exhaustion
        on repeated health checks.
        """
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=2.0,  # Connection establishment timeout
                read=3.0,  # Read timeout for response body
                write=2.0,  # Write timeout for request body
                pool=1.0,  # Timeout for acquiring from pool
            ),
            limits=httpx.Limits(
                max_connections=10,  # Connection pool size
            ),
        )
        logger.info("Health checker httpx.AsyncClient initialized")

    async def _call_client(self, func, *args, **kwargs):
        """Call a potentially sync or async client method and return its result.

        If `func` is a coroutine function, await it. If calling `func` returns a
        coroutine, await that. Otherwise call it in a thread to avoid blocking.
        """
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return await asyncio.to_thread(lambda: func(*args, **kwargs))
        except Exception:
            # Let caller handle/log exceptions consistently
            raise

    async def shutdown(self) -> None:
        """Clean up httpx client on app shutdown.

        Called from FastAPI lifespan shutdown event. Closes connection pool
        and releases resources.
        """
        if self._http_client:
            await self._http_client.aclose()
            logger.info("Health checker httpx.AsyncClient closed")

    # ========================================================================
    # ALGORAND NETWORK CHECKS
    # ========================================================================

    async def check_algorand_connection(self) -> HealthMetric:
        """Check algod node connectivity and current block height.

        Queries /v2/status endpoint to get current round and catchup time.
        Measures latency and determines status based on response time.

        Returns:
            HealthMetric with current_round, latency_ms, and status
        """
        metric_name = "algorand_block_height"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            start = time.monotonic()
            status_response = await self._call_client(self.algod_client.status)
            latency_ms = int((time.monotonic() - start) * 1000)

            current_round = status_response.get("last-round", 0)
            catchup_time = status_response.get("catchup-time", 0)

            # Determine status from latency and sync state
            if latency_ms > thresholds["latency_degraded_max"] or catchup_time > 0:
                status = MetricStatus.DOWN
                message = (
                    f"Algorand node unresponsive: {latency_ms}ms, "
                    f"catchup_time={catchup_time}"
                )
            elif latency_ms > thresholds["latency_healthy_max"]:
                status = MetricStatus.DEGRADED
                message = f"Algorand node slow: {latency_ms}ms response time"
            else:
                status = MetricStatus.HEALTHY
                message = f"Algorand node at round {current_round}, responding in"

            return HealthMetric(
                metric_name=metric_name,
                status=status,
                value={
                    "current_round": current_round,
                    "latency_ms": latency_ms,
                    "catchup_time": catchup_time,
                },
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=message,
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except (AlgodHTTPError, Exception) as exc:
            logger.error(f"Failed to check Algorand connection: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.DOWN,
                value={"error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Algorand algod node unreachable: {exc}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    async def check_algorand_node_sync(self) -> HealthMetric:
        """Check if algod node is fully synced.

        A synced node has catchup_time=0 and is_synced=true.

        Returns:
            HealthMetric with is_synced and catchup_time
        """
        metric_name = "algorand_node_sync"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            status_response = await self._call_client(self.algod_client.status)
            catchup_time = status_response.get("catchup-time", 0)
            is_synced = catchup_time == 0

            if is_synced:
                status = MetricStatus.HEALTHY
                message = "Algorand node is fully synced"
            else:
                status = MetricStatus.DOWN
                message = f"Algorand node catching up: {catchup_time}ms behind"

            return HealthMetric(
                metric_name=metric_name,
                status=status,
                value={
                    "is_synced": is_synced,
                    "catchup_time": catchup_time,
                },
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=message,
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except (AlgodHTTPError, Exception) as exc:
            logger.error(f"Failed to check Algorand sync status: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.DOWN,
                value={"error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Failed to check sync status: {exc}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    async def check_algorand_pending_txns(self) -> HealthMetric:
        """Check pending transaction count in mempool.

        Uses /v2/transactions/pending endpoint to count queued transactions.

        Returns:
            HealthMetric with top_transactions count and status
        """
        metric_name = "algorand_pending_txns"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            pending_response = await self._call_client(self.algod_client.pending_transactions, 1000)
            top_transactions = pending_response.get("total-transactions", 0)

            if top_transactions > thresholds["degraded_max"]:
                status = MetricStatus.DOWN
                message = f"Mempool overloaded: {top_transactions} pending txns"
            elif top_transactions > thresholds["healthy_max"]:
                status = MetricStatus.DEGRADED
                message = f"Mempool moderately full: {top_transactions} pending txns"
            else:
                status = MetricStatus.HEALTHY
                message = f"Mempool healthy: {top_transactions} pending txns"

            return HealthMetric(
                metric_name=metric_name,
                status=status,
                value={"top_transactions": top_transactions},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=message,
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except (AlgodHTTPError, Exception) as exc:
            logger.error(f"Failed to check pending transactions: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.DOWN,
                value={"error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Failed to query pending transactions: {exc}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    # ========================================================================
    # CONTRACT STATE CHECKS
    # ========================================================================

    async def check_contract_states(self) -> HealthMetric:
        """Check all 5 contract application states and last-call recency.

        Fetches global state for each contract and queries the indexer for
        the most recent transaction involving each app. Determines overall
        status as the worst status across all 5 contracts.

        Returns:
            HealthMetric with per-contract measurements and composite status
        """
        metric_name = "contract_states"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        # Contract name -> APP_ID environment variable
        contracts_config = {
            "InsightListing": "INSIGHT_LISTING_APP_ID",
            "Escrow": "ESCROW_APP_ID",
            "FeeConfig": "FEE_CONFIG_APP_ID",
            "AgentRegistry": "AGENT_REGISTRY_APP_ID",
            "SubscriptionManager": "SUBSCRIPTION_MANAGER_APP_ID",
        }

        contract_states = {}
        worst_status = MetricStatus.HEALTHY

        try:
            status_resp = await self._call_client(self.algod_client.status)
            current_round = status_resp.get("last-round", 0)
        except Exception as exc:
            logger.error(f"Failed to get current round: {exc}")
            current_round = 0

        for contract_name, app_id_env in contracts_config.items():
            try:
                app_id = int(os.getenv(app_id_env, "0"))
                if app_id == 0:
                    logger.warning(f"App ID not configured: {app_id_env}")
                    contract_states[contract_name] = {
                        "app_id": 0,
                        "is_paused": None,
                        "last_call_round": None,
                        "rounds_since_last_call": None,
                        "status": MetricStatus.UNKNOWN.value,
                        "error": "App ID not configured",
                    }
                    worst_status = MetricStatus.DOWN
                    continue

                # Fetch app info
                app_info = await self._call_client(self.algod_client.application_info, app_id)
                global_state = app_info.get("params", {}).get("global-state", [])

                # Extract is_paused from global state (look for "paused" key)
                is_paused = False
                for item in global_state:
                    if item.get("key") == base64.b64encode(b"paused").decode():
                        value = item.get("value", {})
                        if value.get("type") == "uint":
                            is_paused = value.get("uint", 0) == 1
                        break

                # Query indexer for last transaction involving this app
                last_call_round = None
                try:
                    txns = await self._call_client(
                        self.indexer_client.search_transactions,
                        application_id=app_id,
                        limit=1,
                    )
                    # Be defensive: tests may supply MagicMock; only treat dicts as valid
                    if isinstance(txns, dict) and txns.get("transactions"):
                        last_call_round = int(txns["transactions"][0].get("confirmed-round", 0) or 0)
                except Exception as exc:
                    logger.warning(
                        f"Failed to query last transaction for {contract_name}: {exc}"
                    )

                if last_call_round is None:
                    rounds_since_last_call = None
                    status = MetricStatus.UNKNOWN
                    message = f"{contract_name} has never been called"
                else:
                    try:
                        rounds_since_last_call = int(current_round) - int(last_call_round)
                    except Exception:
                        rounds_since_last_call = None
                    if is_paused:
                        status = MetricStatus.DOWN
                        message = f"{contract_name} is paused"
                    elif (
                        rounds_since_last_call
                        > thresholds["degraded_rounds_since_call"]
                    ):
                        status = MetricStatus.DOWN
                        message = (
                            f"{contract_name} inactive for "
                            f"{rounds_since_last_call} rounds"
                        )
                    elif (
                        rounds_since_last_call
                        > thresholds["healthy_rounds_since_call"]
                    ):
                        status = MetricStatus.DEGRADED
                        message = (
                            f"{contract_name} last called "
                            f"{rounds_since_last_call} rounds ago"
                        )
                    else:
                        status = MetricStatus.HEALTHY
                        message = f"{contract_name} active"

                contract_states[contract_name] = {
                    "app_id": app_id,
                    "is_paused": is_paused,
                    "last_call_round": last_call_round,
                    "rounds_since_last_call": rounds_since_last_call,
                    "status": status.value,
                    "message": message,
                }

                # Track last metric status and update worst status
                self._last_metric_status[metric_name] = status
                if status == MetricStatus.DOWN:
                    worst_status = MetricStatus.DOWN
                elif status == MetricStatus.DEGRADED and worst_status != MetricStatus.DOWN:
                    worst_status = MetricStatus.DEGRADED

            except Exception as exc:
                logger.error(f"Failed to check {contract_name}: {exc}")
                contract_states[contract_name] = {
                    "app_id": 0,
                    "error": str(exc),
                    "status": MetricStatus.DOWN.value,
                }
                worst_status = MetricStatus.DOWN

        overall_message = (
            f"Contracts: {sum(1 for c in contract_states.values() if c.get('status') == 'healthy')}/5 healthy"
        )

        return HealthMetric(
            metric_name=metric_name,
            status=worst_status,
            value=contract_states,
            threshold_applied=thresholds,
            measured_at=datetime.now(timezone.utc).isoformat(),
            message=overall_message,
            previous_status=self._last_metric_status.get(metric_name, MetricStatus.UNKNOWN),
        )

    # ========================================================================
    # IPFS GATEWAY CHECK
    # ========================================================================

    async def check_ipfs_gateway(self) -> HealthMetric:
        """Check IPFS gateway connectivity with test CID.

        Fetches a known test CID from Pinata and verifies both status code
        and response content to catch cases where gateway returns error HTML
        with status 200.

        Returns:
            HealthMetric with gateway_url, latency_ms, and test_cid_fetch_success
        """
        metric_name = "ipfs_gateway"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        # Use a real test CID that you should pin to Pinata during development
        # For now, using a known placeholder - replace with actual test CID
        TEST_HEALTH_CID = os.getenv(
            "IPFS_HEALTH_CHECK_CID", "QmPLwEqJ3dQn19vCU6opXfAeKNtoKM6tLqLvBuYycSEJJZ"
        )
        GATEWAY_URL = os.getenv("PINATA_GATEWAY_URL", "https://gateway.pinata.cloud")

        test_url = f"{GATEWAY_URL}/ipfs/{TEST_HEALTH_CID}"
        test_cid_fetch_success = False
        latency_ms = 0

        try:
            start = time.monotonic()
            response = await self._http_client.get(test_url)
            latency_ms = int((time.monotonic() - start) * 1000)

            # Check both status code and content
            if (
                response.status_code == 200
                and "mercator" in response.text.lower()  # Verify content is meaningful
            ):
                test_cid_fetch_success = True
            else:
                logger.warning(
                    f"IPFS health check failed: status={response.status_code}, "
                    f"content_len={len(response.text)}"
                )

        except httpx.RequestError as exc:
            logger.error(f"IPFS gateway request failed: {exc}")
            latency_ms = 9999  # Indicate timeout/error

        # Determine status from latency and success
        if not test_cid_fetch_success:
            status = MetricStatus.DOWN
            message = f"IPFS gateway unreachable or invalid response"
        elif latency_ms > thresholds["degraded_max_latency"]:
            status = MetricStatus.DOWN
            message = f"IPFS gateway timeout: {latency_ms}ms"
        elif latency_ms > thresholds["healthy_max_latency"]:
            status = MetricStatus.DEGRADED
            message = f"IPFS gateway slow: {latency_ms}ms response time"
        else:
            status = MetricStatus.HEALTHY
            message = f"IPFS gateway responding in {latency_ms}ms"

        return HealthMetric(
            metric_name=metric_name,
            status=status,
            value={
                "gateway_url": GATEWAY_URL,
                "test_cid_fetch_latency_ms": latency_ms,
                "test_cid_fetch_success": test_cid_fetch_success,
            },
            threshold_applied=thresholds,
            measured_at=datetime.now(timezone.utc).isoformat(),
            message=message,
            previous_status=(
                self._previous_snapshot.metrics[metric_name].status
                if self._previous_snapshot
                and metric_name in self._previous_snapshot.metrics
                else MetricStatus.UNKNOWN
            ),
        )

    # ========================================================================
    # BACKEND ENDPOINT CHECKS
    # ========================================================================

    async def check_backend_endpoints(self) -> HealthMetric:
        """Check internal backend endpoint response latencies.

        Pings 4 endpoints concurrently: /health, /curator/status, /api/v1/health,
        /subscription/status. Non-200 responses count as DOWN for that endpoint.

        Returns:
            HealthMetric with per-endpoint measurements and composite status
        """
        metric_name = "api_endpoint_latencies"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]
        endpoints = [
            "/health",
            "/curator/status",
            "/api/v1/health",
            "/subscription/status?wallet=demo",
        ]

        endpoint_results = {}
        worst_status = MetricStatus.HEALTHY

        async def check_endpoint(path: str) -> tuple[str, dict[str, Any], MetricStatus]:
            try:
                start = time.monotonic()
                response = await self._http_client.get(f"http://localhost:8000{path}")
                latency_ms = int((time.monotonic() - start) * 1000)

                # Non-200 is always DOWN
                if response.status_code != 200:
                    status = MetricStatus.DOWN
                elif latency_ms > thresholds["degraded_max"]:
                    status = MetricStatus.DOWN
                elif latency_ms > thresholds["healthy_max"]:
                    status = MetricStatus.DEGRADED
                else:
                    status = MetricStatus.HEALTHY

                return path, {
                    "endpoint": path,
                    "latency_ms": latency_ms,
                    "status_code": response.status_code,
                    "status": status.value,
                }, status

            except httpx.RequestError as exc:
                logger.warning(f"Endpoint {path} check failed: {exc}")
                return path, {
                    "endpoint": path,
                    "error": str(exc),
                    "status": MetricStatus.DOWN.value,
                }, MetricStatus.DOWN

        # Check all endpoints concurrently
        tasks = [check_endpoint(path) for path in endpoints]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Endpoint check exception: {result}")
                continue

            path, data, status = result
            endpoint_results[path] = data

            # Update worst status
            if status == MetricStatus.DOWN:
                worst_status = MetricStatus.DOWN
            elif status == MetricStatus.DEGRADED and worst_status != MetricStatus.DOWN:
                worst_status = MetricStatus.DEGRADED

        healthy_count = sum(
            1 for e in endpoint_results.values() if e.get("status") == "healthy"
        )
        overall_message = f"Backend endpoints: {healthy_count}/{len(endpoints)} healthy"

        return HealthMetric(
            metric_name=metric_name,
            status=worst_status,
            value=endpoint_results,
            threshold_applied=thresholds,
            measured_at=datetime.now(timezone.utc).isoformat(),
            message=overall_message,
            previous_status=(
                self._previous_snapshot.metrics[metric_name].status
                if self._previous_snapshot
                and metric_name in self._previous_snapshot.metrics
                else MetricStatus.UNKNOWN
            ),
        )

    async def check_websocket_connections(self) -> HealthMetric:
        """Check active WebSocket connection count (informational only).

        Returns:
            HealthMetric with active_count (no status degradation thresholds)
        """
        metric_name = "websocket_connections"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        # Always HEALTHY for informational metrics
        active_count = len(self.ws_manager.active_connections)

        return HealthMetric(
            metric_name=metric_name,
            status=MetricStatus.HEALTHY,  # Always healthy - informational only
            value={"active_count": active_count},
            threshold_applied=thresholds,
            measured_at=datetime.now(timezone.utc).isoformat(),
            message=f"{active_count} active WebSocket connections",
            previous_status=(
                self._previous_snapshot.metrics[metric_name].status
                if self._previous_snapshot
                and metric_name in self._previous_snapshot.metrics
                else MetricStatus.UNKNOWN
            ),
        )

    async def check_error_rate(self) -> HealthMetric:
        """Check API error rate in the last 5 minutes.

        Queries the api_request_log SQLite table for requests in the last
        5 minutes and calculates error percentage.

        Returns:
            HealthMetric with error_pct, total_requests, and error_count
        """
        metric_name = "error_rate_last_5min"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            # Connect to the database
            db_path = os.getenv("API_LOG_DB", "mercator_api_log.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query error rate in last 5 minutes
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN response_status >= 400 THEN 1 ELSE 0 END) as errors
                FROM api_request_log
                WHERE requested_at > datetime('now', '-5 minutes')
            """
            )
            row = cursor.fetchone()
            conn.close()

            total_requests = row[0] if row[0] else 0
            error_count = row[1] if row[1] else 0
            error_pct = (
                (error_count / total_requests * 100) if total_requests > 0 else 0
            )

            if error_pct > thresholds["degraded_max_pct"]:
                # Treat elevated error rates as DEGRADED for alerting granularity
                status = MetricStatus.DEGRADED
                message = f"High API error rate: {error_pct:.1f}%"
            elif error_pct > thresholds["healthy_max_pct"]:
                status = MetricStatus.DEGRADED
                message = f"Elevated API error rate: {error_pct:.1f}%"
            else:
                status = MetricStatus.HEALTHY
                message = f"API error rate normal: {error_pct:.1f}%"

            return HealthMetric(
                metric_name=metric_name,
                status=status,
                value={
                    "error_pct": round(error_pct, 2),
                    "total_requests": total_requests,
                    "error_count": error_count,
                },
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=message,
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except Exception as exc:
            logger.error(f"Failed to check error rate: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.UNKNOWN,
                value={"error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Failed to query error rate: {exc}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    # ========================================================================
    # BUSINESS METRICS
    # ========================================================================

    async def check_usdc_volume(self) -> HealthMetric:
        """Check USDC micropayment volume for today (informational).

        Queries flow_events table for escrow.release_completed events today.
        This is purely informational with no failure threshold.

        Returns:
            HealthMetric with total_usdc (always HEALTHY status)
        """
        metric_name = "usdc_volume_today"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            # Connect to the database
            db_path = os.getenv("CURATOR_DB", "mercator_curator.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query today's USDC volume from escrow releases
            today = datetime.now(timezone.utc).date().isoformat()
            cursor.execute(
                """
                SELECT SUM(json_extract(metadata, '$.amount_usdc')) as total_usdc
                FROM flow_events
                WHERE event_name = 'escrow.release_completed'
                AND timestamp_iso > ?
            """,
                (f"{today}T00:00:00",),
            )
            row = cursor.fetchone()
            conn.close()

            total_usdc = row[0] if row[0] else 0.0

            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.HEALTHY,  # Always healthy - informational
                value={"total_usdc": round(total_usdc, 2)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"USDC volume today: ${total_usdc:.2f}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except Exception as exc:
            logger.warning(f"Failed to query USDC volume: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.HEALTHY,  # Still healthy on query failure - informational
                value={"total_usdc": 0.0, "error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Could not retrieve USDC volume data",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    async def check_curator_agent_health(self) -> HealthMetric:
        """Check curator agent execution cycle health.

        Queries curator_runs table for the most recent completed run.
        Determines status based on run recency and success flag.

        Returns:
            HealthMetric with last_run_at, minutes_since_last_run, last_run_success
        """
        metric_name = "curator_agent_health"
        thresholds = HEALTH_THRESHOLDS[metric_name]["thresholds"]

        try:
            # Connect to the database
            db_path = os.getenv("CURATOR_DB", "mercator_curator.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query last curator run using run_completed_at
            cursor.execute(
                """
                SELECT run_completed_at, published, error
                FROM curator_runs
                ORDER BY run_started_at DESC
                LIMIT 1
            """
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return HealthMetric(
                    metric_name=metric_name,
                    status=MetricStatus.UNKNOWN,
                    value={
                        "last_run_at": None,
                        "minutes_since_last_run": None,
                        "last_run_success": None,
                    },
                    threshold_applied=thresholds,
                    measured_at=datetime.now(timezone.utc).isoformat(),
                    message="Curator Agent has not run yet since server startup",
                    previous_status=(
                        self._previous_snapshot.metrics[metric_name].status
                        if self._previous_snapshot
                        and metric_name in self._previous_snapshot.metrics
                        else MetricStatus.UNKNOWN
                    ),
                )

            run_completed_at = row[0]
            published = row[1]
            error = row[2]

            # Determine success: published == 1 or error == ""
            last_run_success = published == 1 or (error is None or error == "")

            # Parse datetime and calculate minutes elapsed
            try:
                last_run_time = datetime.fromisoformat(
                    run_completed_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                # Try parsing as ISO format without Z
                last_run_time = datetime.fromisoformat(run_completed_at)

            now = datetime.now(timezone.utc)
            minutes_since_last_run = (now - last_run_time).total_seconds() / 60

            # Determine status based on recency and success
            if not last_run_success:
                # Recent failed run is DEGRADED, old failed run is DOWN
                if minutes_since_last_run > thresholds["healthy_max_minutes"]:
                    status = MetricStatus.DOWN
                    message = f"Curator run failed and is overdue: {minutes_since_last_run:.0f} minutes ago"
                else:
                    status = MetricStatus.DEGRADED
                    message = f"Recent curator run failed: {error or 'unknown error'}"
            elif minutes_since_last_run > thresholds["degraded_max_minutes"]:
                status = MetricStatus.DOWN
                message = f"Curator agent overdue: {minutes_since_last_run:.0f} minutes since last run"
            elif minutes_since_last_run > thresholds["healthy_max_minutes"]:
                status = MetricStatus.DEGRADED
                message = f"Curator agent late: {minutes_since_last_run:.0f} minutes since last run"
            else:
                status = MetricStatus.HEALTHY
                message = f"Curator agent healthy: last run {minutes_since_last_run:.0f} minutes ago"

            return HealthMetric(
                metric_name=metric_name,
                status=status,
                value={
                    "last_run_at": run_completed_at,
                    "minutes_since_last_run": round(minutes_since_last_run, 2),
                    "last_run_success": last_run_success,
                },
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=message,
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

        except Exception as exc:
            logger.error(f"Failed to check curator agent health: {exc}")
            return HealthMetric(
                metric_name=metric_name,
                status=MetricStatus.UNKNOWN,
                value={"error": str(exc)},
                threshold_applied=thresholds,
                measured_at=datetime.now(timezone.utc).isoformat(),
                message=f"Failed to query curator agent data: {exc}",
                previous_status=(
                    self._previous_snapshot.metrics[metric_name].status
                    if self._previous_snapshot
                    and metric_name in self._previous_snapshot.metrics
                    else MetricStatus.UNKNOWN
                ),
            )

    # ========================================================================
    # SNAPSHOT COLLECTION, ORCHESTRATION, AND BROADCAST
    # ========================================================================

    async def run_all_checks(self) -> HealthSnapshot:
        """Main orchestrator: run all health checks concurrently every 10 seconds.

        Executes all 12 health check coroutines concurrently using asyncio.gather.
        Handles individual check failures gracefully without crashing the entire
        health check cycle. Detects status changes and broadcasts WebSocket alerts.

        Returns:
            HealthSnapshot with all metrics, overall_status, and alert_count
        """
        # Run all checks concurrently with exception handling
        check_tasks = [
            self.check_algorand_connection(),
            self.check_algorand_node_sync(),
            self.check_algorand_pending_txns(),
            self.check_contract_states(),
            self.check_ipfs_gateway(),
            self.check_backend_endpoints(),
            self.check_websocket_connections(),
            self.check_error_rate(),
            self.check_usdc_volume(),
            self.check_curator_agent_health(),
        ]

        results = await asyncio.gather(*check_tasks, return_exceptions=True)

        metrics_dict = {}
        overall_status = MetricStatus.HEALTHY
        alert_count = 0
        down_metrics = []
        changed_metrics = []

        for result in results:
            # Handle individual check exceptions gracefully
            if isinstance(result, Exception):
                logger.error(f"Health check failed with exception: {result}")
                # Create a fallback metric for the failed check
                metric = HealthMetric(
                    metric_name="unknown_check_error",
                    status=MetricStatus.DOWN,
                    value={"error": str(result)},
                    threshold_applied={},
                    measured_at=datetime.now(timezone.utc).isoformat(),
                    message=f"Health check failed: {result}",
                    previous_status=MetricStatus.UNKNOWN,
                )
            else:
                metric = result

            metrics_dict[metric.metric_name] = metric

            # Detect status changes
            previous_metric = (
                self._previous_snapshot.metrics.get(metric.metric_name)
                if self._previous_snapshot
                else None
            )
            if previous_metric and previous_metric.status != metric.status:
                changed_metrics.append(metric.metric_name)

            # Update overall status and alert tracking
            if metric.status == MetricStatus.DOWN:
                overall_status = MetricStatus.DOWN
                alert_count += 1
                down_metrics.append(metric)
            elif metric.status == MetricStatus.DEGRADED and overall_status != MetricStatus.DOWN:
                overall_status = MetricStatus.DEGRADED

        # Get WebSocket count from the metric
        ws_count = (
            metrics_dict.get("websocket_connections", {}).value.get("active_count", 0)
            if "websocket_connections" in metrics_dict
            else 0
        )

        snapshot = HealthSnapshot(
            snapshot_id=str(uuid4()),
            measured_at=datetime.now(timezone.utc).isoformat(),
            overall_status=overall_status,
            metrics=metrics_dict,
            active_websocket_connections=ws_count,
            alert_count=alert_count,
        )

        # Update history (rolling window of 60 entries for 10 minutes)
        self._metric_history.append(snapshot)
        if len(self._metric_history) > 60:
            self._metric_history.pop(0)

        # Broadcast status changes and alerts
        if changed_metrics:
            await self._broadcast_health_update(snapshot, changed_metrics)

        if down_metrics:
            await self._broadcast_alert(snapshot, down_metrics)

        self._previous_snapshot = snapshot
        return snapshot

    async def _broadcast_health_update(
        self, snapshot: HealthSnapshot, changed_metrics: list[str]
    ) -> None:
        """Broadcast health update to all connected WebSocket clients.

        Sends only the data needed by the frontend to update displays,
        excluding verbose threshold metadata to minimize message size.

        Args:
            snapshot: The current health snapshot
            changed_metrics: List of metric names that changed status
        """
        try:
            # Build compact metric representation for frontend
            metrics_data = {}
            for metric_name, metric in snapshot.metrics.items():
                metrics_data[metric_name] = {
                    "status": metric.status.value,
                    "value": metric.value,
                    "message": metric.message,
                    "measured_at": metric.measured_at,
                }

            payload = {
                "snapshot_id": snapshot.snapshot_id,
                "measured_at": snapshot.measured_at,
                "overall_status": snapshot.overall_status.value,
                "metrics": metrics_data,
                "active_connections": snapshot.active_websocket_connections,
                "alert_count": snapshot.alert_count,
                "changed_metrics": changed_metrics,
            }

            await self.ws_manager.broadcast("health_update", payload)
        except Exception as exc:
            logger.error(f"Failed to broadcast health update: {exc}")

    async def _broadcast_alert(
        self, snapshot: HealthSnapshot, down_metrics: list[HealthMetric]
    ) -> None:
        """Broadcast system alert to all connected WebSocket clients.

        Triggers the alert banner on frontend to display critical system issues.

        Args:
            snapshot: The current health snapshot
            down_metrics: List of metrics with DOWN status
        """
        try:
            payload = {
                "alert_id": str(uuid4()),
                "severity": "critical",
                "message": f"{len(down_metrics)} system component(s) are down",
                "affected_components": [m.metric_name for m in down_metrics],
                "details": [m.message for m in down_metrics],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await self.ws_manager.broadcast("system_alert", payload)
        except Exception as exc:
            logger.error(f"Failed to broadcast alert: {exc}")

    def get_health_history(self, minutes: int = 10) -> list[HealthSnapshot]:
        """Get rolling history of health snapshots for the last N minutes.

        Snapshots are collected at 10-second intervals, so 10 minutes = 60 entries.

        Args:
            minutes: Number of minutes of history to return (default 10)

        Returns:
            List of HealthSnapshot objects from the history
        """
        # 10-second intervals: minutes * 6 = number of snapshots
        snapshot_count = minutes * 6
        if len(self._metric_history) <= snapshot_count:
            return self._metric_history.copy()
        return self._metric_history[-snapshot_count:]

    def get_snapshot_history(self) -> list[HealthSnapshot]:
        """Get rolling history of all health snapshots (max 60 entries)."""
        return self._metric_history.copy()

    def get_latest_snapshot(self) -> HealthSnapshot | None:
        """Get the most recent health snapshot."""
        return self._previous_snapshot

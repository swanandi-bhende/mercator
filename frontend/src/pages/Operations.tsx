import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../utils/api'
import type {
  OpsOverviewResponse,
  OpsEndpointMetric,
  OpsEvent,
  OpsSyntheticResult,
  OpsEndpointHeatCell,
  OpsCacheStatsResponse,
  TraceSessionSummary,
} from '../types'
import { useAppContext } from '../context/AppContext'
import { useOutletContext } from 'react-router-dom'
import type { LayoutOutletContext } from '../components/Layout'

type SeverityFilter = 'all' | 'error' | 'warning' | 'recovery' | 'info'
type TimeFilter = '15m' | '1h' | '24h' | 'all'

// Health Metrics Types
interface HealthMetricData {
  name: string
  status: 'healthy' | 'degraded' | 'down' | 'unknown'
  value: Record<string, unknown>
  message: string
  measured_at?: string
}

interface HealthSnapshot {
  snapshot_id: string
  measured_at: string
  overall_status: 'healthy' | 'degraded' | 'down' | 'unknown'
  metrics: Record<string, HealthMetricData>
  active_connections: number
  alert_count: number
  changed_metrics?: string[]
}

function fmtPct(value: number) {
  return `${Math.max(0, Math.min(100, value)).toFixed(1)}%`
}

function toLocal(iso: string | null) {
  if (!iso) return 'Never'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? 'Unknown' : d.toLocaleString()
}

function relative(iso: string) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'Unknown'
  const mins = Math.max(1, Math.floor((Date.now() - d.getTime()) / 60000))
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function severityTone(value: string) {
  if (value === 'error') return 'bad'
  if (value === 'warning') return 'warn'
  if (value === 'recovery') return 'good'
  return 'neutral'
}

function metricTone(rate: number) {
  if (rate >= 98) return 'good'
  if (rate >= 90) return 'warn'
  return 'bad'
}

function timeWindowMatch(timestamp: string, filter: TimeFilter) {
  if (filter === 'all') return true
  const now = Date.now()
  const ts = new Date(timestamp).getTime()
  if (Number.isNaN(ts)) return false
  const deltaMs = now - ts
  if (filter === '15m') return deltaMs <= 15 * 60 * 1000
  if (filter === '1h') return deltaMs <= 60 * 60 * 1000
  return deltaMs <= 24 * 60 * 60 * 1000
}

function buildConfigBlob(data: OpsOverviewResponse | null) {
  if (!data) return ''
  return JSON.stringify(
    {
      timestamp: data.timestamp,
      network: data.environment.network,
      warning: data.environment.warning,
      contracts: data.environment.contracts,
      wallets: data.environment.wallets,
      redacted_config: data.environment.redacted_config,
    },
    null,
    2,
  )
}

function fmtDuration(ms: number) {
  if (!Number.isFinite(ms)) return 'n/a'
  if (ms < 1000) return `${ms.toFixed(0)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function makeDownload(filename: string, content: string, mime = 'application/json;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function OperationsPage() {
  const { setIsOperator, setOperatorKey } = useAppContext()

  const [overview, setOverview] = useState<OpsOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null)
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  const [expandedHeatCell, setExpandedHeatCell] = useState<string | null>(null)
  const [expandedSynthetic, setExpandedSynthetic] = useState<string | null>(null)
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('24h')
  const [apiKeyInput, setApiKeyInput] = useState<string>(typeof window !== 'undefined' ? localStorage.getItem('operatorKey') || '' : '')
  const [activeApiKey, setActiveApiKey] = useState<string>(typeof window !== 'undefined' ? localStorage.getItem('operatorKey') || '' : '')
  const [adminKeyInput, setAdminKeyInput] = useState<string>(typeof window !== 'undefined' ? localStorage.getItem('adminKey') || '' : '')
  const [authorized, setAuthorized] = useState(false)
  const [accessMessage, setAccessMessage] = useState('')
  const [sessionExpiresAt, setSessionExpiresAt] = useState<number>(typeof window !== 'undefined' ? Number(localStorage.getItem('operatorSessionUntil') || 0) : 0)
  const [isRunningSynthetic, setIsRunningSynthetic] = useState(false)
  const [syntheticHistory, setSyntheticHistory] = useState<OpsSyntheticResult[]>([])
  const [ipfsUploadContent, setIpfsUploadContent] = useState('Mercator operator IPFS test upload')
  const [pingBusyEndpoint, setPingBusyEndpoint] = useState<string | null>(null)
  const [debugMode, setDebugMode] = useState(false)
  const [frontendErrors, setFrontendErrors] = useState<string[]>([])
  const [opsNotes, setOpsNotes] = useState<string>(typeof window !== 'undefined' ? localStorage.getItem('opsOperatorNotes') || '' : '')
  const [cacheStats, setCacheStats] = useState<OpsCacheStatsResponse | null>(null)
  const [cacheStatsLoading, setCacheStatsLoading] = useState(false)
  const [traceSessions, setTraceSessions] = useState<TraceSessionSummary[]>([])
  const [traceSessionsLoading, setTraceSessionsLoading] = useState(false)
  const [traceSessionsError, setTraceSessionsError] = useState<string | null>(null)
  const [curatorTriggerLoading, setCuratorTriggerLoading] = useState(false)
  const [curatorTriggerMessage, setCuratorTriggerMessage] = useState<string | null>(null)
  const [curatorTriggerResults, setCuratorTriggerResults] = useState<Array<Record<string, unknown>>>([])
  const [apiKeyOwnerName, setApiKeyOwnerName] = useState('')
  const [apiKeyOwnerEmail, setApiKeyOwnerEmail] = useState('')
  const [apiKeyTier, setApiKeyTier] = useState('developer')
  const [apiKeyPlaintext, setApiKeyPlaintext] = useState('')
  const [generatedApiKey, setGeneratedApiKey] = useState<{
    keyId: string
    plaintextKey: string
    ownerName: string
    ownerEmail: string
    tier: string
  } | null>(null)

  // Health Metrics State
  const [healthSnapshot, setHealthSnapshot] = useState<HealthSnapshot | null>(null)
  const [healthHistory, setHealthHistory] = useState<HealthSnapshot[]>([])
  const [curatorCountdown, setCuratorCountdown] = useState<number>(0)
  const [systemAlertLog, setSystemAlertLog] = useState<Array<{ id: string; message: string; timestamp: string }>>([])
  const { latestWsEvent } = useOutletContext<LayoutOutletContext>()

  const isSessionValid = sessionExpiresAt > Date.now()

  const activateSession = (ttlMinutes = 30) => {
    const next = Date.now() + ttlMinutes * 60 * 1000
    setSessionExpiresAt(next)
    localStorage.setItem('operatorSessionUntil', String(next))
  }

  const clearSession = () => {
    setSessionExpiresAt(0)
    setAuthorized(false)
    setOverview(null)
    localStorage.removeItem('operatorSessionUntil')
    setIsOperator(false)
  }

  const logout = () => {
    clearSession()
    setActiveApiKey('')
    setApiKeyInput('')
    localStorage.removeItem('operatorKey')
    setOperatorKey(null)
    setAccessMessage('Logged out. Operator access has been revoked for this browser session.')
  }

  const persistAdminKey = (nextKey: string) => {
    setAdminKeyInput(nextKey)
    if (typeof window !== 'undefined') {
      if (nextKey.trim()) {
        localStorage.setItem('adminKey', nextKey.trim())
      } else {
        localStorage.removeItem('adminKey')
      }
    }
  }

  const checkAccess = async (apiKey?: string) => {
    try {
      const response = await api.operationsAccessCheck(apiKey)
      if (response.access.authorized) {
        setAuthorized(true)
        setAccessMessage(response.access.reason)
        setIsOperator(true)
        if (apiKey?.trim()) {
          localStorage.setItem('operatorKey', apiKey.trim())
          setOperatorKey(apiKey.trim())
          setActiveApiKey(apiKey.trim())
        }
        activateSession(30)
        return true
      }
      setAuthorized(false)
      setAccessMessage(response.access.reason)
      return false
    } catch (err) {
      const msg = err instanceof ApiError ? err.userMessage : 'Operator access denied. Localhost or valid API key required.'
      setAuthorized(false)
      setAccessMessage(msg)
      return false
    }
  }

  const loadOverview = async (verifyOnChain = true) => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.operationsOverviewSecure({ verifyOnChain, apiKey: activeApiKey || undefined })
      setOverview(response)
      setSyntheticHistory(response.synthetic_recent || [])
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.userMessage : err instanceof Error ? err.message : 'Failed to load operations overview'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const loadCacheStats = async () => {
    try {
      setCacheStatsLoading(true)
      const response = await api.adminCacheStats()
      setCacheStats(response)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'Failed to load cache stats')
    } finally {
      setCacheStatsLoading(false)
    }
  }

  const loadTraceSessions = async () => {
    try {
      setTraceSessionsLoading(true)
      setTraceSessionsError(null)
      const response = await api.tracesLatest(8)
      setTraceSessions(response.sessions || [])
    } catch (err) {
      setTraceSessions([])
      setTraceSessionsError(err instanceof ApiError ? err.userMessage : 'Failed to load trace sessions')
    } finally {
      setTraceSessionsLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    const init = async () => {
      const ok = await checkAccess(activeApiKey || undefined)
      if (!active || !ok) return
      await Promise.all([loadOverview(true), loadCacheStats(), loadTraceSessions()])
      try {
        const history = await api.operationsSyntheticHistory(activeApiKey || undefined)
        if (active) setSyntheticHistory(history.results)
      } catch {
        // no-op
      }
    }
    init()

    const timer = window.setInterval(() => {
      if (authorized && isSessionValid) {
        loadOverview(false)
      }
    }, 15000)

    const sessionTimer = window.setInterval(() => {
      if (sessionExpiresAt && sessionExpiresAt <= Date.now()) {
        clearSession()
        setAccessMessage('Operator session expired. Re-authenticate to continue.')
      }
    }, 1000)

    return () => {
      active = false
      window.clearInterval(timer)
      window.clearInterval(sessionTimer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!debugMode) return

    const onWindowError = (event: ErrorEvent) => {
      setFrontendErrors((prev) => [`${new Date().toLocaleTimeString()} [error] ${event.message}`, ...prev].slice(0, 60))
    }
    const onPromiseError = (event: PromiseRejectionEvent) => {
      const message = event.reason instanceof Error ? event.reason.message : String(event.reason)
      setFrontendErrors((prev) => [`${new Date().toLocaleTimeString()} [rejection] ${message}`, ...prev].slice(0, 60))
    }

    window.addEventListener('error', onWindowError)
    window.addEventListener('unhandledrejection', onPromiseError)
    return () => {
      window.removeEventListener('error', onWindowError)
      window.removeEventListener('unhandledrejection', onPromiseError)
    }
  }, [debugMode])

  useEffect(() => {
    localStorage.setItem('opsOperatorNotes', opsNotes)
  }, [opsNotes])

  // Fetch initial health snapshot
  useEffect(() => {
    const fetchHealthSnapshot = async () => {
      try {
        const response = await fetch('/ops/health/snapshot')
        const data = await response.json()
        setHealthSnapshot(data)
      } catch (err) {
        console.error('Failed to fetch health snapshot:', err)
      }
    }
    fetchHealthSnapshot()
    // Fetch again every 15 seconds as fallback if WebSocket isn't updating
    const interval = setInterval(fetchHealthSnapshot, 15000)
    return () => clearInterval(interval)
  }, [])

  // Listen for WebSocket health_update events
  useEffect(() => {
    if (latestWsEvent?.type === 'health_update' && latestWsEvent.data) {
      setHealthSnapshot(latestWsEvent.data)
      // Add to system alert log if there are DOWN metrics
      if (latestWsEvent.data.alert_count > 0) {
        const downMetrics = Object.entries(latestWsEvent.data.metrics)
          .filter(([_, metric]) => metric.status === 'down')
          .map(([name, _]) => name)
          .join(', ')
        if (downMetrics) {
          setSystemAlertLog((prev) => [
            ...prev,
            {
              id: latestWsEvent.data.snapshot_id,
              message: `Alert: ${downMetrics} are down`,
              timestamp: latestWsEvent.data.measured_at,
            },
          ])
        }
      }
    }
  }, [latestWsEvent])

  // Curator countdown timer
  useEffect(() => {
    const interval = setInterval(() => {
      if (healthSnapshot?.metrics?.curator_agent_health) {
        const lastRunAt = new Date(healthSnapshot.metrics.curator_agent_health.value?.last_run_at as string || Date.now())
        const nextRunTime = new Date(lastRunAt.getTime() + 35 * 60 * 1000)
        const secondsUntilNext = Math.max(0, Math.floor((nextRunTime.getTime() - Date.now()) / 1000))
        setCuratorCountdown(secondsUntilNext)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [healthSnapshot])

  // Fetch health history
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await fetch('/ops/health/history?minutes=10')
        const data = await response.json()
        setHealthHistory(Array.isArray(data) ? data : [])
      } catch (err) {
        console.error('Failed to fetch health history:', err)
      }
    }
    fetchHistory()
  }, [healthSnapshot])

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'is-good'
      case 'degraded':
        return 'is-warn'
      case 'down':
        return 'is-bad'
      default:
        return 'is-neutral'
    }
  }

  const triggerHealthRefresh = async () => {
    try {
      const response = await fetch('/admin/health/refresh', { method: 'POST' })
      const data = await response.json()
      setHealthSnapshot(data)
    } catch (err) {
      console.error('Failed to refresh health:', err)
    }
  }

  const metrics = overview?.request_metrics || []
  const contracts = overview?.contracts || []
  const environment = overview?.environment
  const heatmap = overview?.endpoint_heatmap || []
  const ipfs = overview?.ipfs
  const algorand = overview?.algorand

  const filteredEvents = useMemo(() => {
    const events = overview?.events || []
    return events.filter((event) => {
      if (severityFilter !== 'all' && event.severity !== severityFilter) return false
      return timeWindowMatch(event.timestamp, timeFilter)
    })
  }, [overview, severityFilter, timeFilter])

  const exportEvents = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      time_filter: timeFilter,
      severity_filter: severityFilter,
      events: filteredEvents,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mercator-system-events-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const runSynthetic = async () => {
    if (!authorized || !isSessionValid) return
    setIsRunningSynthetic(true)
    try {
      const response = await api.operationsRunSyntheticTest({}, activeApiKey || undefined)
      setSyntheticHistory(response.history)
      await loadOverview(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'Synthetic test failed')
    } finally {
      setIsRunningSynthetic(false)
    }
  }

  const testIpfsUpload = async () => {
    if (!authorized || !isSessionValid) return
    try {
      await api.operationsIpfsTestUpload({ content: ipfsUploadContent }, activeApiKey || undefined)
      await loadOverview(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'IPFS test upload failed')
    }
  }

  const testAlgorandConnection = async () => {
    if (!authorized || !isSessionValid) return
    try {
      await api.operationsAlgorandTest(activeApiKey || undefined)
      await loadOverview(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'Algorand connection test failed')
    }
  }

  const pingEndpoint = async (endpoint: string) => {
    if (!authorized || !isSessionValid) return
    setPingBusyEndpoint(endpoint)
    try {
      await api.operationsPingEndpoint(endpoint, activeApiKey || undefined)
      await loadOverview(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : `Endpoint ping failed for ${endpoint}`)
    } finally {
      setPingBusyEndpoint(null)
    }
  }

  const exportDiagnosticsBundle = async () => {
    if (!authorized || !isSessionValid) return
    try {
      const response = await api.operationsDiagnosticsBundle({ includeContractScan: false, apiKey: activeApiKey || undefined })
      makeDownload(
        `mercator-diagnostics-${new Date().toISOString().slice(0, 10)}.json`,
        JSON.stringify(response.bundle, null, 2),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'Diagnostics export failed')
    }
  }

  const refreshAdminState = async () => {
    await Promise.all([loadOverview(true), loadCacheStats(), loadTraceSessions()])
  }

  const downloadTraceSession = (sessionId: string) => {
    const url = api.traceDownloadUrl(sessionId)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const triggerCuratorNow = async () => {
    if (!authorized || !isSessionValid) return
    setCuratorTriggerLoading(true)
    setCuratorTriggerMessage(null)
    try {
      const response = await api.adminCuratorTriggerNow(adminKeyInput || undefined)
      setCuratorTriggerResults(response.results || [])
      setCuratorTriggerMessage(`Curator trigger completed with ${response.results?.length || 0} result(s).`)
      await refreshAdminState()
    } catch (err) {
      setCuratorTriggerResults([])
      setCuratorTriggerMessage(err instanceof ApiError ? err.userMessage : 'Curator trigger failed')
    } finally {
      setCuratorTriggerLoading(false)
    }
  }

  const generateApiKey = async () => {
    if (!authorized || !isSessionValid) return
    if (!apiKeyOwnerName.trim() || !apiKeyOwnerEmail.trim()) {
      setError('Owner name and email are required to generate an API key.')
      return
    }

    try {
      const response = await api.adminGenerateApiKey(
        {
          owner_name: apiKeyOwnerName.trim(),
          owner_email: apiKeyOwnerEmail.trim(),
          tier: apiKeyTier,
          ...(apiKeyPlaintext.trim() ? { plaintext_key: apiKeyPlaintext.trim() } : {}),
        },
        adminKeyInput || undefined,
      )
      setGeneratedApiKey({
        keyId: response.key_id,
        plaintextKey: response.plaintext_key,
        ownerName: response.owner_name,
        ownerEmail: response.owner_email,
        tier: response.tier,
      })
      setError(null)
      setAccessMessage(`Generated API key for ${response.owner_name}.`)
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : 'API key generation failed')
    }
  }

  const copyConfig = async () => {
    const blob = buildConfigBlob(overview)
    if (!blob) return
    try {
      await navigator.clipboard.writeText(blob)
    } catch {
      // No-op fallback.
    }
  }

  const activateApiKeyAccess = async () => {
    const ok = await checkAccess(apiKeyInput || undefined)
    if (!ok) return
    await loadOverview(true)
  }

  const sessionRemainingSec = Math.max(0, Math.floor((sessionExpiresAt - Date.now()) / 1000))

  if (!authorized || !isSessionValid) {
    return (
      <div className="activity-page">
        <section className="activity-hero">
          <div className="home-wrap activity-shell">
            <article className="activity-head-card">
              <p className="home-kicker">Operations / Restricted</p>
              <h1>Operator access required</h1>
              <p>
                This dashboard is restricted to authorized operators. Access is granted from localhost or with a valid API key.
              </p>
              <div className="ops-access-box">
                <label>
                  <span>Operator API Key</span>
                  <input
                    type="password"
                    placeholder="Enter x-api-key"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                  />
                </label>
                <div className="activity-report-actions">
                  <button className="activity-action-btn is-primary" onClick={activateApiKeyAccess}>
                    Authenticate Operator
                  </button>
                </div>
                {accessMessage && (
                  <div className="activity-empty">
                    <h3>Access status</h3>
                    <p>{accessMessage}</p>
                  </div>
                )}
              </div>
            </article>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="activity-page">
      <section className="activity-hero">
        <div className="home-wrap activity-shell">
          <article className="activity-head-card">
            <p className="home-kicker">Operations / Health</p>
            <h1>Real-time control center for contracts, APIs, storage, and infrastructure.</h1>
            <p>
              Verify live on-chain contract state, endpoint performance, environment readiness, and rolling system events without leaving Mercator.
            </p>
            <div className="activity-report-actions">
              <button className="activity-action-btn is-primary" onClick={() => loadOverview(true)}>
                {loading ? 'Refreshing...' : 'Refresh Dashboard'}
              </button>
              <button className="activity-action-btn" onClick={exportDiagnosticsBundle}>
                Export Diagnostics Bundle
              </button>
              <button className="activity-action-btn" onClick={() => window.location.assign('/activity')}>
                Open Activity Ledger
              </button>
            </div>
            <div className="ops-session-strip">
              <span className="activity-status is-good">Operator Mode Active</span>
              <span>Session valid for {Math.floor(sessionRemainingSec / 60)}m {sessionRemainingSec % 60}s</span>
              <button className="activity-action-btn" onClick={() => activateSession(30)}>Extend Session</button>
              <button className="activity-action-btn" onClick={clearSession}>End Session</button>
              <button className="activity-action-btn" onClick={logout}>Logout</button>
            </div>
            {lastUpdated && <div className="activity-sync-note"><strong>Last update</strong><span>{lastUpdated} (auto-refresh every 15s)</span></div>}
            {error && <div className="activity-empty"><h3>Operations warning</h3><p>{error}</p></div>}
          </article>

          <article className="ops-admin-card">
            <p className="home-kicker">Admin / Operator Tools</p>
            <h3>Trigger curator, inspect cache health, and mint API keys.</h3>

            <div className="ops-admin-keybar">
              <label>
                <span>Admin key</span>
                <input
                  type="password"
                  placeholder="Enter X-Admin-Key"
                  value={adminKeyInput}
                  onChange={(event) => persistAdminKey(event.target.value)}
                />
              </label>
              <div className="activity-report-actions">
                <button className="activity-action-btn is-primary" onClick={triggerCuratorNow} disabled={curatorTriggerLoading}>
                  {curatorTriggerLoading ? 'Triggering...' : 'Trigger Curator Now'}
                </button>
                <button className="activity-action-btn" onClick={loadCacheStats} disabled={cacheStatsLoading}>
                  {cacheStatsLoading ? 'Loading Cache Stats...' : 'Refresh Cache Stats'}
                </button>
                <button className="activity-action-btn" onClick={refreshAdminState}>
                  Refresh Ops Data
                </button>
              </div>
            </div>

            {curatorTriggerMessage && <div className="ops-admin-message">{curatorTriggerMessage}</div>}

            {curatorTriggerResults.length > 0 && (
              <div className="ops-admin-result-list">
                {curatorTriggerResults.slice(0, 5).map((result, index) => (
                  <article key={`curator-${index}`} className="ops-admin-result-item">
                    <strong>Result {index + 1}</strong>
                    <pre>{JSON.stringify(result, null, 2)}</pre>
                  </article>
                ))}
              </div>
            )}

            <div className="ops-cache-grid">
              {(['profile_cache', 'reputation_cache', 'listings_cache'] as const).map((key) => {
                const stat = cacheStats?.[key]
                return (
                  <article key={key} className="ops-cache-card">
                    <span>{key.replace('_', ' ')}</span>
                    <strong>{stat?.present ? 'Present' : 'Missing'}</strong>
                    <p>
                      Size: {typeof stat?.size === 'number' ? stat.size : 'n/a'} · Max size: {typeof stat?.maxsize === 'number' ? stat.maxsize : 'n/a'}
                    </p>
                  </article>
                )
              })}
            </div>

            <div className="ops-trace-downloads">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="home-kicker">Telemetry Traces</p>
                  <h4>Download recent flow traces</h4>
                </div>
                <button className="activity-action-btn" onClick={loadTraceSessions} disabled={traceSessionsLoading}>
                  {traceSessionsLoading ? 'Loading Traces...' : 'Refresh Traces'}
                </button>
              </div>
              {traceSessionsError && <div className="ops-admin-message">{traceSessionsError}</div>}
              <div className="ops-trace-list">
                {traceSessions.length === 0 && !traceSessionsLoading ? (
                  <div className="activity-empty">
                    <h3>No trace sessions found</h3>
                    <p>Run a purchase or listing flow to generate downloadable traces.</p>
                  </div>
                ) : (
                  traceSessions.map((session) => (
                    <article key={session.session_id} className="ops-trace-card">
                      <div>
                        <strong>{session.session_id}</strong>
                        <p>
                          {session.event_count} event{session.event_count === 1 ? '' : 's'} · {toLocal(session.last_event)}
                        </p>
                      </div>
                      <button className="activity-action-btn is-primary" onClick={() => downloadTraceSession(session.session_id)}>
                        Download Trace
                      </button>
                    </article>
                  ))
                )}
              </div>
            </div>

            <div className="ops-api-key-form">
              <label>
                <span>Owner name</span>
                <input value={apiKeyOwnerName} onChange={(event) => setApiKeyOwnerName(event.target.value)} placeholder="Curator Team" />
              </label>
              <label>
                <span>Owner email</span>
                <input value={apiKeyOwnerEmail} onChange={(event) => setApiKeyOwnerEmail(event.target.value)} placeholder="ops@mercator.io" />
              </label>
              <label>
                <span>Tier</span>
                <select value={apiKeyTier} onChange={(event) => setApiKeyTier(event.target.value)}>
                  <option value="demo">demo</option>
                  <option value="developer">developer</option>
                  <option value="enterprise">enterprise</option>
                </select>
              </label>
              <label>
                <span>Optional plaintext key</span>
                <input value={apiKeyPlaintext} onChange={(event) => setApiKeyPlaintext(event.target.value)} placeholder="Leave blank to auto-generate" />
              </label>
              <button className="activity-action-btn is-primary" onClick={generateApiKey}>
                Generate API Key
              </button>
            </div>

            {generatedApiKey && (
              <div className="ops-api-key-result">
                <h4>Generated API key</h4>
                <p><strong>Owner:</strong> {generatedApiKey.ownerName} · {generatedApiKey.ownerEmail} · {generatedApiKey.tier}</p>
                <p><strong>Key ID:</strong> {generatedApiKey.keyId}</p>
                <p><strong>Plaintext key:</strong> {generatedApiKey.plaintextKey}</p>
              </div>
            )}
          </article>

          {/* ===== HEALTH METRICS DASHBOARD ===== */}
          {healthSnapshot && (
            <>
              {/* Overall Health Banner */}
              <article className={`ops-health-banner is-${getStatusColor(healthSnapshot.overall_status)}`}>
                <div className="ops-health-header">
                  <div>
                    <p className="home-kicker">System Health Status</p>
                    <h2>
                      {healthSnapshot.overall_status === 'healthy' && '🟢 All Systems Healthy'}
                      {healthSnapshot.overall_status === 'degraded' && '🟡 Some Systems Degraded'}
                      {healthSnapshot.overall_status === 'down' && '🔴 Critical Issues Detected'}
                      {healthSnapshot.overall_status === 'unknown' && '⚫ Status Unknown'}
                    </h2>
                  </div>
                  <div className="ops-health-actions">
                    <span className="ops-alert-badge">{healthSnapshot.alert_count} alert{healthSnapshot.alert_count !== 1 ? 's' : ''}</span>
                    <small>{new Date(healthSnapshot.measured_at).toLocaleTimeString()}</small>
                    <button className="activity-action-btn" onClick={triggerHealthRefresh}>
                      Refresh Now
                    </button>
                  </div>
                </div>
              </article>

              {/* Algorand Network Section */}
              <article className="ops-metrics-group">
                <p className="home-kicker">Algorand Network</p>
                <div className="ops-metrics-grid">
                  {healthSnapshot.metrics.algorand_block_height && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.algorand_block_height.status)}`}>
                      <h4>Block Height</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">{(healthSnapshot.metrics.algorand_block_height.value as any)?.current_round || 'N/A'}</span>
                        <span className="ops-metric-unit">ms</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.algorand_block_height.message}</p>
                    </div>
                  )}
                  {healthSnapshot.metrics.algorand_node_sync && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.algorand_node_sync.status)}`}>
                      <h4>Node Sync</h4>
                      <div className="ops-metric-value">
                        <span>{(healthSnapshot.metrics.algorand_node_sync.value as any)?.is_synced ? '✓ Synced' : '✗ Not Synced'}</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.algorand_node_sync.message}</p>
                    </div>
                  )}
                  {healthSnapshot.metrics.algorand_pending_txns && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.algorand_pending_txns.status)}`}>
                      <h4>Pending Txns</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">{(healthSnapshot.metrics.algorand_pending_txns.value as any)?.top_transactions || 0}</span>
                        <span className="ops-metric-unit">txns</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.algorand_pending_txns.message}</p>
                    </div>
                  )}
                </div>
              </article>

              {/* Contracts Section */}
              {healthSnapshot.metrics.contract_states && (
                <article className="ops-metrics-group">
                  <p className="home-kicker">Smart Contracts</p>
                  <div className="ops-contracts-grid">
                    {Object.entries((healthSnapshot.metrics.contract_states.value as any) || {}).map(([contractName, contractData]: [string, any]) => (
                      <div key={contractName} className={`ops-contract-card is-${getStatusColor(contractData?.status || 'unknown')}`}>
                        <h4>{contractName}</h4>
                        <div className="ops-contract-details">
                          {contractData?.app_id && <span>App ID: {contractData.app_id}</span>}
                          {contractData?.is_paused !== undefined && (
                            <span className={`ops-pause-badge is-${contractData.is_paused ? 'bad' : 'good'}`}>
                              {contractData.is_paused ? '⏸ Paused' : '▶ Running'}
                            </span>
                          )}
                          {contractData?.rounds_since_last_call !== undefined && (
                            <span>{contractData.rounds_since_last_call} rounds ago (~{Math.floor(contractData.rounds_since_last_call * 4.5 / 60)} min)</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              )}

              {/* Infrastructure Section */}
              <article className="ops-metrics-group">
                <p className="home-kicker">Infrastructure</p>
                <div className="ops-infra-grid">
                  {healthSnapshot.metrics.ipfs_gateway && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.ipfs_gateway.status)}`}>
                      <h4>IPFS Gateway</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">{(healthSnapshot.metrics.ipfs_gateway.value as any)?.test_cid_fetch_latency_ms || 'N/A'}</span>
                        <span className="ops-metric-unit">ms</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.ipfs_gateway.message}</p>
                    </div>
                  )}
                  {healthSnapshot.metrics.api_endpoint_latencies && (
                    <div className="ops-endpoints-card">
                      <h4>API Endpoints</h4>
                      <div className="ops-endpoints-list">
                        {Object.entries((healthSnapshot.metrics.api_endpoint_latencies.value as any) || {}).map(([endpoint, data]: [string, any]) => (
                          <div key={endpoint} className={`ops-endpoint-item is-${getStatusColor(data?.status || 'unknown')}`}>
                            <span className="ops-endpoint-name">{endpoint}</span>
                            <span className="ops-endpoint-latency">{data?.latency_ms || 'N/A'}ms</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {healthSnapshot.metrics.error_rate_last_5min && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.error_rate_last_5min.status)}`}>
                      <h4>Error Rate (5m)</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">{((healthSnapshot.metrics.error_rate_last_5min.value as any)?.error_pct || 0).toFixed(1)}</span>
                        <span className="ops-metric-unit">%</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.error_rate_last_5min.message}</p>
                    </div>
                  )}
                </div>
              </article>

              {/* Business Metrics Section */}
              <article className="ops-metrics-group">
                <p className="home-kicker">Business Metrics</p>
                <div className="ops-business-grid">
                  {healthSnapshot.metrics.usdc_volume_today && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.usdc_volume_today.status)}`}>
                      <h4>USDC Volume Today</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">${((healthSnapshot.metrics.usdc_volume_today.value as any)?.total_micro_usdc || 0) / 1000000}</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.usdc_volume_today.message}</p>
                    </div>
                  )}
                  {healthSnapshot.metrics.curator_agent_health && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.curator_agent_health.status)}`}>
                      <h4>Curator Agent</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-text">Next run in {Math.floor(curatorCountdown / 60)}m {curatorCountdown % 60}s</span>
                      </div>
                      <p className="ops-metric-message">Last run: {(healthSnapshot.metrics.curator_agent_health.value as any)?.last_run_at ? new Date((healthSnapshot.metrics.curator_agent_health.value as any)?.last_run_at).toLocaleTimeString() : 'Never'}</p>
                    </div>
                  )}
                  {healthSnapshot.metrics.websocket_connections && (
                    <div className={`ops-metric-card is-${getStatusColor(healthSnapshot.metrics.websocket_connections.status)}`}>
                      <h4>WebSocket Connections</h4>
                      <div className="ops-metric-value">
                        <span className="ops-metric-number">{(healthSnapshot.metrics.websocket_connections.value as any)?.active_count || 0}</span>
                        <span className="ops-metric-unit">clients</span>
                      </div>
                      <p className="ops-metric-message">{healthSnapshot.metrics.websocket_connections.message}</p>
                    </div>
                  )}
                </div>
              </article>

              {/* System Events Timeline */}
              {systemAlertLog.length > 0 && (
                <article className="ops-events-timeline">
                  <p className="home-kicker">Health Alerts (Last 10 minutes)</p>
                  <div className="ops-alert-feed">
                    {systemAlertLog.slice(-10).reverse().map((alert) => (
                      <div key={alert.id} className="ops-alert-item">
                        <span className="ops-alert-time">{new Date(alert.timestamp).toLocaleTimeString()}</span>
                        <span className="ops-alert-text">{alert.message}</span>
                      </div>
                    ))}
                  </div>
                </article>
              )}
            </>
          )}

          <article className="ops-synthetic-card">
            <p className="home-kicker">Synthetic Transaction Tester</p>
            <h3>Validate listing, storage, chain confirmation, purchase, and delivery in one click.</h3>
            <div className="activity-report-actions">
              <button className="activity-action-btn is-primary" onClick={runSynthetic} disabled={isRunningSynthetic}>
                {isRunningSynthetic ? 'Running Test...' : 'Run Full Synthetic Test'}
              </button>
            </div>
            <div className="ops-synth-list">
              {syntheticHistory.map((run) => (
                <article key={run.id} className={`ops-synth-item is-${run.status === 'passed' ? 'good' : 'bad'}`}>
                  <div className="ops-synth-head">
                    <strong>{run.id}</strong>
                    <span className={`activity-status is-${run.status === 'passed' ? 'good' : 'bad'}`}>{run.status}</span>
                  </div>
                  <small>{toLocal(run.timestamp)} · Total: {fmtDuration(run.total_duration_ms)}</small>
                  {run.stopped_on && <p>Stopped on: {run.stopped_on}</p>}
                  {run.error && <p>{run.error}</p>}
                  <button className="activity-action-btn" onClick={() => setExpandedSynthetic(expandedSynthetic === run.id ? null : run.id)}>
                    {expandedSynthetic === run.id ? 'Hide Steps' : 'Show Steps'}
                  </button>
                  {expandedSynthetic === run.id && (
                    <ul>
                      {run.steps.map((step) => (
                        <li key={`${run.id}-${step.name}`}>
                          <strong>{step.name}</strong> · {step.status} · {fmtDuration(step.duration_ms)} · {step.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
          </article>

          <article className="ops-ipfs-card">
            <p className="home-kicker">IPFS Gateway Health</p>
            <div className="ops-ipfs-grid">
              <div className="ops-ipfs-main">
                <h3>
                  Status: <span className={`activity-status is-${ipfs?.status === 'healthy' ? 'good' : ipfs?.status === 'warning' ? 'warn' : 'bad'}`}>{ipfs?.status || 'unknown'}</span>
                </h3>
                <p>Latency: {fmtDuration(ipfs?.latency_ms || 0)} (slow over {fmtDuration(ipfs?.slow_threshold_ms || 0)})</p>
                <p>Recent upload success: {fmtPct(ipfs?.upload_success_rate || 0)}</p>
                <p>Fallback gateways: {(ipfs?.fallback_gateways || []).length ? (ipfs?.fallback_gateways || []).join(', ') : 'None configured'}</p>
                <div className="ops-trend-chart" aria-hidden="true">
                  {(ipfs?.trend || []).map((point, idx) => (
                    <span
                      key={`ipfs-trend-${idx}`}
                      title={`${point.success ? 'success' : 'fail'} · ${point.latency_ms}ms`}
                      style={{
                        height: `${Math.max(8, Math.min(100, 100 - (point.latency_ms / Math.max(1, ipfs?.slow_threshold_ms || 2500)) * 100))}%`,
                        opacity: point.success ? 0.95 : 0.35,
                      }}
                    />
                  ))}
                </div>
              </div>
              <div className="ops-ipfs-test">
                <label>
                  <span>Test upload payload</span>
                  <textarea value={ipfsUploadContent} onChange={(e) => setIpfsUploadContent(e.target.value)} rows={3} />
                </label>
                <button className="activity-action-btn" onClick={testIpfsUpload}>Run Test Upload</button>
                <ul>
                  {(ipfs?.connection.gateways || []).map((gateway) => (
                    <li key={gateway.url}>{gateway.url} · {gateway.status} · {fmtDuration(gateway.latency_ms)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </article>

          <article className="ops-algorand-card">
            <p className="home-kicker">Algorand TestNet Connection</p>
            <div className="ops-algo-grid">
              <div>
                <h3>Node health: <span className={`activity-status is-${algorand?.status === 'healthy' ? 'good' : algorand?.status === 'warning' ? 'warn' : 'bad'}`}>{algorand?.node_health || 'unknown'}</span></h3>
                <p><strong>Current round:</strong> {algorand?.current_round ?? 0}</p>
                <p><strong>Sync status:</strong> {algorand?.sync_status || 'unknown'}</p>
                <p><strong>Recent activity:</strong> {algorand?.recent_activity_count ?? 0} requests</p>
                <p><strong>Fee suggestion:</strong> {algorand?.fee_suggestion_micro_algo ?? 0} microAlgos</p>
                {algorand?.warning && <p className="ops-warning">{algorand.warning}</p>}
                <button className="activity-action-btn" onClick={testAlgorandConnection}>Run Connection Test</button>
              </div>
              <div className="ops-trend-chart" aria-hidden="true">
                {(algorand?.trend || []).map((point, idx) => (
                  <span
                    key={`algo-trend-${idx}`}
                    title={`round ${point.round} · ${point.synced ? 'synced' : 'catchup'} · ${point.latency_ms}ms`}
                    style={{
                      height: `${Math.max(14, Math.min(100, point.synced ? 92 : 34))}%`,
                      opacity: point.synced ? 0.95 : 0.5,
                    }}
                  />
                ))}
              </div>
            </div>
          </article>

          <article className="ops-heatmap-card">
            <p className="home-kicker">API Endpoint Health Heatmap</p>
            <div className="ops-heatmap-grid">
              {heatmap.map((cell: OpsEndpointHeatCell) => (
                <button
                  key={cell.endpoint}
                  className={`ops-heat-cell is-${cell.tone}`}
                  title={cell.summary}
                  onClick={() => setExpandedHeatCell(expandedHeatCell === cell.endpoint ? null : cell.endpoint)}
                >
                  <strong>{cell.endpoint}</strong>
                  <span>{fmtDuration(cell.latency_ms)} · {fmtPct(cell.success_rate)}</span>
                </button>
              ))}
            </div>
            {expandedHeatCell && (
              <div className="ops-heat-expand">
                <div className="ops-heat-expand-head">
                  <h4>{expandedHeatCell}</h4>
                  <button className="activity-action-btn" onClick={() => pingEndpoint(expandedHeatCell)}>
                    {pingBusyEndpoint === expandedHeatCell ? 'Pinging...' : 'Manual Ping'}
                  </button>
                </div>
                <ul>
                  {(heatmap.find((c) => c.endpoint === expandedHeatCell)?.samples || []).map((sample, idx) => (
                    <li key={`${expandedHeatCell}-${idx}`}>
                      {toLocal(sample.timestamp)} · {sample.method} · {sample.status_code} · {fmtDuration(sample.latency_ms)} · {sample.anon_user}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>

          <article className="ops-contracts-card">
            <p className="home-kicker">Smart Contract Status</p>
            <div className="ops-contracts-grid">
              {contracts.map((contract) => (
                <article key={`${contract.name}-${contract.app_id}`} className={`ops-contract-item is-${contract.status}`}>
                  <div className="ops-contract-head">
                    <h3>{contract.name}</h3>
                    <span className={`activity-status is-${contract.status === 'healthy' ? 'good' : contract.status === 'warning' ? 'warn' : 'bad'}`}>
                      {contract.status}
                    </span>
                  </div>
                  <p><strong>App ID:</strong> {contract.app_id}</p>
                  <p><strong>Creator:</strong> {contract.creator}</p>
                  <p><strong>Approval Hash:</strong> {contract.approval_hash}</p>
                  <p><strong>Total Calls:</strong> {contract.total_calls}</p>
                  <p><strong>Last Call:</strong> {toLocal(contract.last_call)}</p>
                  <p><strong>Current State:</strong> {contract.state}</p>
                  <div className="ops-contract-actions">
                    <button className="activity-action-btn" onClick={() => loadOverview(true)}>
                      Verify On-Chain
                    </button>
                    {contract.explorer_url && (
                      <a href={contract.explorer_url} target="_blank" rel="noreferrer">
                        Open Explorer
                      </a>
                    )}
                  </div>
                  {contract.errors.length > 0 && (
                    <ul className="ops-error-list">
                      {contract.errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
          </article>

          <article className="ops-metrics-card">
            <p className="home-kicker">Request / Response Metrics</p>
            <div className="ops-metrics-grid">
              {metrics.map((metric: OpsEndpointMetric) => (
                <article key={metric.endpoint} className="ops-metric-item">
                  <div className="ops-metric-head">
                    <h3>{metric.endpoint}</h3>
                    <span className={`activity-status is-${metricTone(metric.success_rate)}`}>{fmtPct(metric.success_rate)}</span>
                  </div>
                  <div className="ops-metric-values">
                    <p><strong>Latency:</strong> {metric.latency_ms.toFixed(2)} ms</p>
                    <p><strong>Throughput:</strong> {metric.throughput_rpm.toFixed(2)} req/min</p>
                    <p><strong>Recent Errors:</strong> {metric.recent_errors.reduce((sum, e) => sum + e.count, 0)}</p>
                  </div>
                  <div className="ops-trend-chart" aria-hidden="true">
                    {metric.trend.map((point, idx) => (
                      <span
                        key={`${metric.endpoint}-${idx}`}
                        title={`Throughput ${point.throughput}, Success ${point.success_rate}%`}
                        style={{
                          height: `${Math.max(14, Math.min(100, point.success_rate))}%`,
                          opacity: point.throughput > 0 ? 0.95 : 0.35,
                        }}
                      />
                    ))}
                  </div>
                  <button
                    className="activity-action-btn"
                    onClick={() => setExpandedMetric(expandedMetric === metric.endpoint ? null : metric.endpoint)}
                  >
                    {expandedMetric === metric.endpoint ? 'Hide Error Logs' : 'Show Error Logs'}
                  </button>

                  {expandedMetric === metric.endpoint && (
                    <div className="ops-metric-errors">
                      {metric.recent_errors.length === 0 ? (
                        <p>No recent errors for this endpoint.</p>
                      ) : (
                        metric.recent_errors.map((group) => (
                          <article key={`${metric.endpoint}-${group.category}`}>
                            <h4>{group.category} · {group.count}</h4>
                            <ul>
                              {group.logs.map((log, idx) => (
                                <li key={`${group.category}-${idx}`}>
                                  {toLocal(log.timestamp)} · {log.latency_ms.toFixed(2)}ms · {log.anon_user}
                                </li>
                              ))}
                            </ul>
                          </article>
                        ))
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </article>

          <article className="ops-env-card">
            <p className="home-kicker">Environment & Configuration</p>
            <div className="activity-empty">
              <h3>{environment?.network || 'Unknown network'}</h3>
              <p>{environment?.warning || 'Network warning unavailable'}</p>
            </div>
            <div className="ops-env-grid">
              <div>
                <h4>Configured Contracts</h4>
                <ul>
                  {Object.entries(environment?.contracts || {}).map(([k, v]) => (
                    <li key={k}><strong>{k}:</strong> {v}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Connected Wallets</h4>
                <ul>
                  {(environment?.wallets || []).map((wallet) => (
                    <li key={wallet.label}>
                      <strong>{wallet.label}:</strong> {wallet.address} · {wallet.algo_balance ?? 'n/a'} ALGO
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Redacted Config</h4>
                <ul>
                  {Object.entries(environment?.redacted_config || {}).map(([k, v]) => (
                    <li key={k}><strong>{k}:</strong> {v}</li>
                  ))}
                </ul>
                <button className="activity-action-btn" onClick={copyConfig}>Copy Config</button>
              </div>
            </div>
          </article>

          <article className="ops-events-card">
            <p className="home-kicker">System Events Timeline</p>
            <div className="ops-events-filters">
              <label>
                <span>Severity</span>
                <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value as SeverityFilter)}>
                  <option value="all">All</option>
                  <option value="error">Error</option>
                  <option value="warning">Warning</option>
                  <option value="recovery">Recovery</option>
                  <option value="info">Info</option>
                </select>
              </label>
              <label>
                <span>Time Window</span>
                <select value={timeFilter} onChange={(e) => setTimeFilter(e.target.value as TimeFilter)}>
                  <option value="15m">Last 15m</option>
                  <option value="1h">Last 1h</option>
                  <option value="24h">Last 24h</option>
                  <option value="all">All</option>
                </select>
              </label>
              <button className="activity-action-btn" onClick={exportEvents}>Export Events</button>
            </div>

            <div className="ops-events-list">
              {filteredEvents.map((event: OpsEvent) => (
                <article key={event.id} className={`ops-event-item is-${severityTone(event.severity)}`}>
                  <div className="ops-event-head">
                    <strong>{event.message}</strong>
                    <span>{relative(event.timestamp)}</span>
                  </div>
                  <small>{event.type} · {toLocal(event.timestamp)}</small>
                  <button
                    className="activity-action-btn"
                    onClick={() => setExpandedEvent(expandedEvent === event.id ? null : event.id)}
                  >
                    {expandedEvent === event.id ? 'Hide Details' : 'Show Details'}
                  </button>
                  {expandedEvent === event.id && (
                    <pre>{JSON.stringify(event.details, null, 2)}</pre>
                  )}
                </article>
              ))}
            </div>
          </article>

          <article className="ops-debug-card">
            <p className="home-kicker">Debug Mode & Operator Notes</p>
            <div className="activity-report-actions">
              <button className="activity-action-btn" onClick={() => setDebugMode((v) => !v)}>
                {debugMode ? 'Disable Debug Console' : 'Enable Debug Console'}
              </button>
              <button className="activity-action-btn" onClick={() => setFrontendErrors([])}>Clear Console</button>
            </div>
            {debugMode && (
              <div className="ops-debug-console">
                {frontendErrors.length === 0 ? (
                  <p>No frontend errors captured yet.</p>
                ) : (
                  <ul>
                    {frontendErrors.map((entry, idx) => (
                      <li key={`err-${idx}`}>{entry}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <label className="ops-notes">
              <span>Operator notes</span>
              <textarea
                rows={5}
                value={opsNotes}
                onChange={(e) => setOpsNotes(e.target.value)}
                placeholder="Track operational context, incident notes, and actions taken..."
              />
            </label>
            <button
              className="activity-action-btn"
              onClick={() =>
                makeDownload(
                  `mercator-ops-notes-${new Date().toISOString().slice(0, 10)}.txt`,
                  opsNotes,
                  'text/plain;charset=utf-8',
                )
              }
            >
              Export Notes
            </button>
          </article>
        </div>
      </section>
    </div>
  )
}

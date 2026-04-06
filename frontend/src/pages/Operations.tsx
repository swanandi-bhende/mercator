import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../utils/api'
import type {
  OpsOverviewResponse,
  OpsEndpointMetric,
  OpsEvent,
  OpsSyntheticResult,
  OpsEndpointHeatCell,
} from '../types'
import { useAppContext } from '../context/AppContext'

type SeverityFilter = 'all' | 'error' | 'warning' | 'recovery' | 'info'
type TimeFilter = '15m' | '1h' | '24h' | 'all'

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
    if (!authorized || !isSessionValid) return
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

  useEffect(() => {
    let active = true
    const init = async () => {
      const ok = await checkAccess(activeApiKey || undefined)
      if (!active || !ok) return
      await loadOverview(true)
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

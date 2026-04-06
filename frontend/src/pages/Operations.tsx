import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../utils/api'
import type { HealthResponse, LedgerRecord } from '../types'

type ServiceKey = 'api' | 'algod' | 'indexer' | 'listing_app' | 'escrow_app'

function fmtPct(v: number) {
  return `${Math.max(0, Math.min(100, v)).toFixed(1)}%`
}

function timeAgo(iso: string) {
  const d = new Date(iso).getTime()
  if (Number.isNaN(d)) return 'Unknown'
  const mins = Math.max(1, Math.floor((Date.now() - d) / 60000))
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function OperationsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [records, setRecords] = useState<LedgerRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<string>('')

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthResponse, ledgerResponse] = await Promise.all([
        api.health(),
        api.ledger({ limit: 120 }),
      ])
      setHealth(healthResponse)
      setRecords(ledgerResponse.records || [])
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.userMessage : err instanceof Error ? err.message : 'Failed to load operations data'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const metrics = useMemo(() => {
    const total = records.length
    const success = records.filter((r) => r.status === 'confirmed' || r.status === 'completed').length
    const failed = records.filter((r) => r.status === 'failed').length
    const pending = records.filter((r) => r.status === 'pending').length
    const successRate = total ? (success / total) * 100 : 0
    const errorRate = total ? (failed / total) * 100 : 0
    const volume = records
      .filter((r) => r.actionType === 'payment_confirmed')
      .reduce((sum, r) => sum + r.amountUsdc, 0)

    return { total, successRate, errorRate, pending, failed, volume }
  }, [records])

  const recentEvents = useMemo(() => records.slice(0, 8), [records])

  const services: ServiceKey[] = ['api', 'algod', 'indexer', 'listing_app', 'escrow_app']

  return (
    <div className="activity-page">
      <section className="activity-hero">
        <div className="home-wrap activity-shell">
          <article className="activity-head-card">
            <p className="home-kicker">Operations / Health</p>
            <h1>Backend status and operational transparency.</h1>
            <p>
              Monitor service health, indexer readiness, and transaction reliability using live backend and ledger telemetry.
            </p>
            <div className="activity-report-actions">
              <button type="button" className="activity-action-btn is-primary" onClick={loadData}>
                {loading ? 'Refreshing...' : 'Refresh Status'}
              </button>
              <button type="button" className="activity-action-btn" onClick={() => window.location.assign('/activity')}>
                Open Activity Ledger
              </button>
            </div>
            {lastRefresh && <div className="activity-sync-note"><strong>Last refresh</strong><span>{lastRefresh}</span></div>}
            {error && <div className="activity-empty"><h3>Health check warning</h3><p>{error}</p></div>}
          </article>

          <article className="activity-metrics-card">
            <p className="home-kicker">Live Metrics</p>
            <div className="activity-metrics-grid">
              <div><span>Total transactions</span><strong>{metrics.total}</strong></div>
              <div><span>Total payment volume</span><strong>{metrics.volume.toFixed(2)} USDC</strong></div>
              <div><span>Success rate</span><strong>{fmtPct(metrics.successRate)}</strong></div>
              <div><span>Error rate</span><strong>{fmtPct(metrics.errorRate)}</strong></div>
              <div><span>Pending tx</span><strong>{metrics.pending}</strong></div>
              <div><span>Failed tx</span><strong>{metrics.failed}</strong></div>
            </div>
          </article>

          <article className="activity-table-card">
            <p className="home-kicker">Component Health</p>
            <div className="activity-detail-grid">
              {services.map((key) => {
                const service = health?.services?.[key]
                const status = service?.status || 'unknown'
                return (
                  <div key={key}>
                    <span>{key.replace('_', ' ')}</span>
                    <strong>{status}</strong>
                    <small>{service?.detail || 'No detail available'}</small>
                  </div>
                )
              })}
            </div>
          </article>

          <article className="activity-table-card">
            <p className="home-kicker">Recent Backend Events</p>
            <table className="activity-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Status</th>
                  <th>Tx ID</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{timeAgo(event.timestampIso)}</td>
                    <td>{event.actionType.replace('_', ' ')}</td>
                    <td>
                      <span className={`activity-status is-${event.status === 'failed' ? 'bad' : event.status === 'pending' ? 'warn' : 'good'}`}>
                        {event.status}
                      </span>
                    </td>
                    <td>
                      <a href={event.explorerUrl} target="_blank" rel="noreferrer">{event.txId}</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </div>
      </section>
    </div>
  )
}

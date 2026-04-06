import { Fragment, useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../context/AppContext'
import { api, ApiError } from '../utils/api'
import type { LedgerRecord as ApiLedgerRecord } from '../types'

type LedgerAction = 'listing_created' | 'payment_confirmed' | 'escrow_released' | 'insight_delivered'
type LedgerStatus = 'confirmed' | 'pending' | 'failed' | 'completed'

type LedgerRecord = ApiLedgerRecord

type ActionFilter = 'all' | LedgerAction
type StatusFilter = 'all' | LedgerStatus
type SortMode = 'newest' | 'oldest' | 'action_az' | 'status'

const LOCAL_LEDGER_KEY = 'mercator_activity_ledger_v1'

const BASE_LEDGER: LedgerRecord[] = [
  {
    id: 'ledger-1',
    timestampIso: '2026-04-05T16:22:00.000Z',
    actionType: 'listing_created',
    seller: 'ALGO...SELLER1',
    buyer: '-',
    amountUsdc: 0.5,
    status: 'confirmed',
    txId: 'TX7A3F9B2C1LST',
    explorerUrl: 'https://explorer.perawallet.app/tx/TX7A3F9B2C1LST/',
    cid: 'QmABC123XYZListing',
    ipfsUrl: 'https://ipfs.io/ipfs/QmABC123XYZListing',
    listingId: 'L-2201',
    contractId: 'insight_listing:2201',
    confirmationRound: 45128302,
    feeAlgo: '0.001',
    escrowStatus: 'not_applicable',
    contentHash: 'sha256:2f1e88f3ad8de49f2be8dcb2bbfe5e9f',
    listingMetadata: 'NIFTY expected to test 24500 resistance today',
  },
  {
    id: 'ledger-2',
    timestampIso: '2026-04-06T08:55:00.000Z',
    actionType: 'payment_confirmed',
    seller: 'ALGO...SELLER1',
    buyer: 'ALGO...BUYER9',
    amountUsdc: 0.5,
    status: 'confirmed',
    txId: 'TX402PAY0001',
    explorerUrl: 'https://explorer.perawallet.app/tx/TX402PAY0001/',
    cid: 'QmABC123XYZListing',
    ipfsUrl: 'https://ipfs.io/ipfs/QmABC123XYZListing',
    listingId: 'L-2201',
    contractId: 'escrow:8044',
    confirmationRound: 45130144,
    feeAlgo: '0.001',
    escrowStatus: 'locked',
    contentHash: 'sha256:2f1e88f3ad8de49f2be8dcb2bbfe5e9f',
    listingMetadata: 'Buyer approval validated. Payment flow started.',
  },
  {
    id: 'ledger-3',
    timestampIso: '2026-04-06T08:56:00.000Z',
    actionType: 'insight_delivered',
    seller: 'ALGO...SELLER1',
    buyer: 'ALGO...BUYER9',
    amountUsdc: 0.5,
    status: 'completed',
    txId: 'TXDLVR0001',
    explorerUrl: 'https://explorer.perawallet.app/tx/TXDLVR0001/',
    cid: 'QmABC123XYZListing',
    ipfsUrl: 'https://ipfs.io/ipfs/QmABC123XYZListing',
    listingId: 'L-2201',
    contractId: 'delivery:proof-v1',
    confirmationRound: 45130161,
    feeAlgo: '0.0005',
    escrowStatus: 'locked',
    contentHash: 'sha256:2f1e88f3ad8de49f2be8dcb2bbfe5e9f',
    listingMetadata: 'IPFS insight retrieved by authorized buyer wallet.',
  },
  {
    id: 'ledger-4',
    timestampIso: '2026-04-06T08:57:00.000Z',
    actionType: 'escrow_released',
    seller: 'ALGO...SELLER1',
    buyer: 'ALGO...BUYER9',
    amountUsdc: 0.5,
    status: 'completed',
    txId: 'TXESCROW0001',
    explorerUrl: 'https://explorer.perawallet.app/tx/TXESCROW0001/',
    cid: 'QmABC123XYZListing',
    ipfsUrl: 'https://ipfs.io/ipfs/QmABC123XYZListing',
    listingId: 'L-2201',
    contractId: 'escrow:8044',
    confirmationRound: 45130174,
    feeAlgo: '0.001',
    escrowStatus: 'released',
    contentHash: 'sha256:2f1e88f3ad8de49f2be8dcb2bbfe5e9f',
    listingMetadata: 'Escrow release executed after delivery confirmation.',
  },
]

function readPersistedLedger() {
  if (typeof window === 'undefined') return [] as LedgerRecord[]
  try {
    const raw = window.localStorage.getItem(LOCAL_LEDGER_KEY)
    if (!raw) return [] as LedgerRecord[]
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as LedgerRecord[]) : ([] as LedgerRecord[])
  } catch {
    return [] as LedgerRecord[]
  }
}

function persistLedger(records: LedgerRecord[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(LOCAL_LEDGER_KEY, JSON.stringify(records))
  } catch {
    // Best effort cache only.
  }
}

function actionLabel(action: LedgerAction) {
  if (action === 'listing_created') return 'Listing created'
  if (action === 'payment_confirmed') return 'Payment confirmed'
  if (action === 'escrow_released') return 'Escrow released'
  return 'Insight delivered'
}

function statusTone(status: LedgerStatus) {
  if (status === 'confirmed' || status === 'completed') return 'good'
  if (status === 'pending') return 'warn'
  return 'bad'
}

function formatTimestamp(iso: string) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'Unknown time' : date.toLocaleString()
}

function toDateInputValue(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toISOString().slice(0, 10)
}

function formatPercent(value: number) {
  return `${Math.max(0, Math.min(100, value)).toFixed(1)}%`
}

function csvSafe(value: string) {
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function downloadTextFile(filename: string, content: string, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function ActivityLedgerPage() {
  const { paymentState, selectedInsight, sellerMetadata, lastTransactionId } = useAppContext()

  const [query, setQuery] = useState('')
  const [actionFilter, setActionFilter] = useState<ActionFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [walletFilter, setWalletFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [backendRecords, setBackendRecords] = useState<LedgerRecord[]>([])
  const [backendStatus, setBackendStatus] = useState<'idle' | 'loading' | 'ready' | 'failed'>('idle')
  const [backendMessage, setBackendMessage] = useState<string>('')

  useEffect(() => {
    let cancelled = false

    const fetchLedger = async () => {
      setBackendStatus('loading')
      setBackendMessage('')
      try {
        const response = await api.ledger({ limit: 500 })
        if (cancelled) return
        if (!response.success) {
          setBackendStatus('failed')
          setBackendMessage(response.error || 'Ledger endpoint returned an error.')
          return
        }

        setBackendRecords(response.records || [])
        setBackendStatus('ready')
        setBackendMessage(`Indexer sync complete: ${response.count} records loaded.`)
      } catch (error) {
        if (cancelled) return
        const message =
          error instanceof ApiError
            ? error.userMessage
            : error instanceof Error
              ? error.message
              : 'Could not fetch backend ledger records.'
        setBackendStatus('failed')
        setBackendMessage(message)
      }
    }

    fetchLedger()
    return () => {
      cancelled = true
    }
  }, [])

  const allRecords = useMemo(() => {
    const persisted = readPersistedLedger()
    const baseSource = backendRecords.length > 0 ? backendRecords : [...persisted, ...BASE_LEDGER]
    let merged = [...baseSource]

    if (paymentState?.txId || paymentState?.paymentTxId || lastTransactionId) {
      const primaryTx = paymentState?.paymentTxId || paymentState?.txId || lastTransactionId || ''
      const escrowTx = paymentState?.escrowTxId || ''
      const cid = paymentState?.ipfsCid || selectedInsight?.cid || 'Unavailable'
      const listingId = paymentState?.listingId || selectedInsight?.listing_id || 'Unknown'
      const seller = sellerMetadata?.address || selectedInsight?.seller_wallet || 'Unknown seller'
      const buyer = 'Buyer wallet (session)'
      const amount = Number(selectedInsight?.price || 0)

      if (primaryTx) {
        merged.push({
          id: `session-payment-${primaryTx}`,
          timestampIso: new Date().toISOString(),
          actionType: 'payment_confirmed',
          seller,
          buyer,
          amountUsdc: amount,
          status: paymentState?.stage === 'failed' ? 'failed' : 'confirmed',
          txId: primaryTx,
          explorerUrl: paymentState?.explorerPaymentUrl || `https://explorer.perawallet.app/tx/${primaryTx}/`,
          cid,
          ipfsUrl: cid && cid !== 'Unavailable' ? `https://ipfs.io/ipfs/${cid}` : '',
          listingId,
          contractId: 'escrow:session',
          confirmationRound: 0,
          feeAlgo: '0.001',
          escrowStatus: escrowTx ? 'locked' : 'pending',
          contentHash: 'sha256:runtime-session',
          listingMetadata: selectedInsight?.insight_text || 'Session purchase event',
          errorMessage: paymentState?.error,
        })
      }

      if (escrowTx) {
        merged.push({
          id: `session-escrow-${escrowTx}`,
          timestampIso: new Date().toISOString(),
          actionType: 'escrow_released',
          seller,
          buyer,
          amountUsdc: amount,
          status: paymentState?.escrowReleased ? 'completed' : 'pending',
          txId: escrowTx,
          explorerUrl: paymentState?.explorerEscrowUrl || `https://explorer.perawallet.app/tx/${escrowTx}/`,
          cid,
          ipfsUrl: cid && cid !== 'Unavailable' ? `https://ipfs.io/ipfs/${cid}` : '',
          listingId,
          contractId: 'escrow:session',
          confirmationRound: 0,
          feeAlgo: '0.001',
          escrowStatus: paymentState?.escrowReleased ? 'released' : 'pending',
          contentHash: 'sha256:runtime-session',
          listingMetadata: 'Escrow outcome derived from session payment state',
          errorMessage: paymentState?.error,
        })
      }

      if (paymentState?.deliveredInsightText) {
        merged.push({
          id: `session-delivery-${primaryTx || listingId}`,
          timestampIso: new Date().toISOString(),
          actionType: 'insight_delivered',
          seller,
          buyer,
          amountUsdc: amount,
          status: paymentState?.stage === 'completed' ? 'completed' : 'pending',
          txId: primaryTx || 'delivery-runtime',
          explorerUrl: paymentState?.explorerPaymentUrl || '',
          cid,
          ipfsUrl: cid && cid !== 'Unavailable' ? `https://ipfs.io/ipfs/${cid}` : '',
          listingId,
          contractId: 'delivery:session',
          confirmationRound: 0,
          feeAlgo: '0.0005',
          escrowStatus: paymentState?.escrowReleased ? 'released' : 'locked',
          contentHash: `sha256:${paymentState.deliveredInsightText.slice(0, 24).replace(/\s+/g, '')}`,
          listingMetadata: paymentState.deliveredInsightText,
          errorMessage: paymentState?.error,
        })
      }
    }

    const deduped = new Map<string, LedgerRecord>()
    for (const record of merged) {
      deduped.set(record.id, record)
    }
    const final = [...deduped.values()]
    persistLedger(final)
    return final
  }, [backendRecords, paymentState, selectedInsight, sellerMetadata, lastTransactionId])

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    const walletTerm = walletFilter.trim().toLowerCase()
    const fromTime = fromDate ? new Date(`${fromDate}T00:00:00`).getTime() : null
    const toTime = toDate ? new Date(`${toDate}T23:59:59`).getTime() : null

    const byFilter = allRecords.filter((record) => {
      if (actionFilter !== 'all' && record.actionType !== actionFilter) return false
      if (statusFilter !== 'all' && record.status !== statusFilter) return false

      const recordTime = new Date(record.timestampIso).getTime()
      if (fromTime !== null && recordTime < fromTime) return false
      if (toTime !== null && recordTime > toTime) return false

      if (walletTerm) {
        const partyText = `${record.seller} ${record.buyer}`.toLowerCase()
        if (!partyText.includes(walletTerm)) return false
      }

      if (!term) return true
      return [
        record.txId,
        record.seller,
        record.buyer,
        record.cid,
        record.listingId,
        record.contractId,
        actionLabel(record.actionType),
      ]
        .join(' ')
        .toLowerCase()
        .includes(term)
    })

    const sorted = [...byFilter]
    sorted.sort((a, b) => {
      if (sortMode === 'newest') {
        return new Date(b.timestampIso).getTime() - new Date(a.timestampIso).getTime()
      }
      if (sortMode === 'oldest') {
        return new Date(a.timestampIso).getTime() - new Date(b.timestampIso).getTime()
      }
      if (sortMode === 'action_az') {
        return actionLabel(a.actionType).localeCompare(actionLabel(b.actionType))
      }
      return a.status.localeCompare(b.status)
    })
    return sorted
  }, [allRecords, query, actionFilter, statusFilter, walletFilter, fromDate, toDate, sortMode])

  const metrics = useMemo(() => {
    const totalCount = filtered.length
    const volume = filtered
      .filter((item) => item.actionType === 'payment_confirmed')
      .reduce((sum, item) => sum + item.amountUsdc, 0)

    const successCount = filtered.filter((item) => item.status === 'confirmed' || item.status === 'completed').length
    const errorCount = filtered.filter((item) => item.status === 'failed').length
    const successRate = totalCount ? (successCount / totalCount) * 100 : 0
    const errorRate = totalCount ? (errorCount / totalCount) * 100 : 0

    const listingDurations: number[] = []
    const listingMap = new Map<string, { payment?: number; escrow?: number }>()
    for (const item of filtered) {
      const current = listingMap.get(item.listingId) || {}
      const time = new Date(item.timestampIso).getTime()
      if (item.actionType === 'payment_confirmed') current.payment = time
      if (item.actionType === 'escrow_released') current.escrow = time
      listingMap.set(item.listingId, current)
    }
    for (const value of listingMap.values()) {
      if (value.payment && value.escrow && value.escrow >= value.payment) {
        listingDurations.push((value.escrow - value.payment) / 60000)
      }
    }
    const avgMinutes =
      listingDurations.length > 0
        ? listingDurations.reduce((sum, d) => sum + d, 0) / listingDurations.length
        : 0

    return {
      totalCount,
      volume,
      avgMinutes,
      successRate,
      errorRate,
    }
  }, [filtered])

  const handleExportCsv = () => {
    const header = [
      'timestamp',
      'action_type',
      'seller',
      'buyer',
      'amount_usdc',
      'status',
      'tx_id',
      'explorer_url',
      'cid',
      'contract_id',
      'listing_id',
      'confirmation_round',
      'fee_algo',
      'escrow_status',
      'content_hash',
      'error_message',
    ].join(',')

    const rows = filtered.map((record) => [
      record.timestampIso,
      record.actionType,
      record.seller,
      record.buyer,
      record.amountUsdc.toFixed(2),
      record.status,
      record.txId,
      record.explorerUrl,
      record.cid,
      record.contractId,
      record.listingId,
      String(record.confirmationRound),
      record.feeAlgo,
      record.escrowStatus,
      record.contentHash,
      record.errorMessage || '',
    ].map(csvSafe).join(','))

    downloadTextFile(
      `mercator-ledger-${new Date().toISOString().slice(0, 10)}.csv`,
      [header, ...rows].join('\n'),
      'text/csv;charset=utf-8',
    )
  }

  const handleGenerateReport = () => {
    const lines = [
      'Mercator Activity Ledger Report',
      `Generated: ${new Date().toISOString()}`,
      `Filters: action=${actionFilter}, status=${statusFilter}, wallet=${walletFilter || 'any'}, from=${fromDate || 'any'}, to=${toDate || 'any'}, query=${query || 'none'}`,
      '',
      'Summary Metrics',
      `- Total transactions: ${metrics.totalCount}`,
      `- Total payment volume (USDC): ${metrics.volume.toFixed(2)}`,
      `- Avg payment->escrow release time: ${metrics.avgMinutes.toFixed(2)} minutes`,
      `- Success rate: ${formatPercent(metrics.successRate)}`,
      `- Error rate: ${formatPercent(metrics.errorRate)}`,
      '',
      'Top Records',
      ...filtered.slice(0, 50).map((record, idx) =>
        `${idx + 1}. ${record.timestampIso} | ${actionLabel(record.actionType)} | ${record.status} | tx=${record.txId} | listing=${record.listingId} | cid=${record.cid}`,
      ),
    ]

    downloadTextFile(
      `mercator-ledger-report-${new Date().toISOString().slice(0, 10)}.txt`,
      lines.join('\n'),
    )
  }

  const handleProofBundleDownload = (record: LedgerRecord) => {
    const bundle = {
      generated_at: new Date().toISOString(),
      proof_type: 'mercator_transaction_bundle',
      transaction: record,
    }
    downloadTextFile(
      `proof-bundle-${record.txId || record.id}.json`,
      JSON.stringify(bundle, null, 2),
      'application/json;charset=utf-8',
    )
  }

  return (
    <div className="activity-page">
      <section className="activity-hero">
        <div className="home-wrap activity-shell">
          <article className="activity-head-card">
            <p className="home-kicker">Activity Ledger</p>
            <h1>Complete audit trail and proof repository.</h1>
            <p>
              Explore Mercator activity in one time-ordered ledger: listing creation, payments,
              escrow releases, and insight delivery events with direct proof links.
            </p>
            <div className="activity-sync-note">
              <strong>
                Source: {backendStatus === 'ready' && backendRecords.length > 0 ? 'Backend indexer' : 'Local/session fallback'}
              </strong>
              <span>
                {backendStatus === 'loading'
                  ? 'Syncing from backend ledger...'
                  : backendMessage || 'No backend sync status available.'}
              </span>
            </div>
          </article>

          <article className="activity-controls-card">
            <div className="activity-controls-grid">
              <label>
                <span>Search tx ID or CID</span>
                <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search tx id, CID, listing, contract"
                />
              </label>

              <label>
                <span>Action type</span>
                <select value={actionFilter} onChange={(event) => setActionFilter(event.target.value as ActionFilter)}>
                  <option value="all">All actions</option>
                  <option value="listing_created">Listing created</option>
                  <option value="payment_confirmed">Payment confirmed</option>
                  <option value="escrow_released">Escrow released</option>
                  <option value="insight_delivered">Insight delivered</option>
                </select>
              </label>

              <label>
                <span>Status</span>
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
                  <option value="all">All status</option>
                  <option value="confirmed">Confirmed</option>
                  <option value="pending">Pending</option>
                  <option value="failed">Failed</option>
                  <option value="completed">Completed</option>
                </select>
              </label>

              <label>
                <span>Wallet address</span>
                <input
                  type="text"
                  value={walletFilter}
                  onChange={(event) => setWalletFilter(event.target.value)}
                  placeholder="Filter seller or buyer"
                />
              </label>

              <label>
                <span>From date</span>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(event) => setFromDate(event.target.value)}
                  max={toDate || undefined}
                />
              </label>

              <label>
                <span>To date</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(event) => setToDate(event.target.value)}
                  min={fromDate || undefined}
                />
              </label>

              <label>
                <span>Sort</span>
                <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                  <option value="action_az">Action A-Z</option>
                  <option value="status">Status</option>
                </select>
              </label>
            </div>

            <div className="activity-report-actions">
              <button type="button" className="activity-action-btn is-primary" onClick={handleExportCsv}>
                Export CSV
              </button>
              <button type="button" className="activity-action-btn" onClick={handleGenerateReport}>
                Generate Date-Range Report
              </button>
              <button
                type="button"
                className="activity-action-btn"
                onClick={() => {
                  setQuery('')
                  setActionFilter('all')
                  setStatusFilter('all')
                  setWalletFilter('')
                  setFromDate('')
                  setToDate('')
                  setSortMode('newest')
                }}
              >
                Reset Filters
              </button>
            </div>
          </article>

          <article className="activity-metrics-card">
            <p className="home-kicker">Cumulative Metrics</p>
            <div className="activity-metrics-grid">
              <div>
                <span>Total Volume</span>
                <strong>{metrics.volume.toFixed(2)} USDC</strong>
              </div>
              <div>
                <span>Total Transactions</span>
                <strong>{metrics.totalCount}</strong>
              </div>
              <div>
                <span>Average Time</span>
                <strong>{metrics.avgMinutes.toFixed(2)} min</strong>
              </div>
              <div>
                <span>Success Rate</span>
                <strong>{formatPercent(metrics.successRate)}</strong>
              </div>
              <div>
                <span>Error Rate</span>
                <strong>{formatPercent(metrics.errorRate)}</strong>
              </div>
              <div>
                <span>Date Scope</span>
                <strong>
                  {(fromDate || toDate)
                    ? `${fromDate || 'start'} to ${toDate || 'today'}`
                    : `${toDateInputValue(allRecords[allRecords.length - 1]?.timestampIso || '') || 'all time'} to ${toDateInputValue(allRecords[0]?.timestampIso || '') || 'today'}`}
                </strong>
              </div>
            </div>
          </article>

          <article className="activity-table-card">
            <div className="activity-table-scroll" role="region" aria-label="Transaction feed">
              <table className="activity-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Parties</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Tx / Proof</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((record) => (
                    <Fragment key={record.id}>
                      <tr
                        className={expandedId === record.id ? 'is-expanded' : ''}
                        onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}
                      >
                        <td>{formatTimestamp(record.timestampIso)}</td>
                        <td>
                          <strong>{actionLabel(record.actionType)}</strong>
                          <small>{record.listingId}</small>
                        </td>
                        <td>
                          <span>S: {record.seller}</span>
                          <span>B: {record.buyer}</span>
                        </td>
                        <td>{record.amountUsdc.toFixed(2)} USDC</td>
                        <td>
                          <span className={`activity-status is-${statusTone(record.status)}`}>{record.status}</span>
                        </td>
                        <td>
                          <a href={record.explorerUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                            {record.txId}
                          </a>
                          <small>{record.contractId}</small>
                        </td>
                      </tr>

                      {expandedId === record.id && (
                        <tr className="activity-detail-row">
                          <td colSpan={6}>
                            <div className="activity-detail-grid">
                              <div>
                                <span>Transaction ID</span>
                                <strong>{record.txId}</strong>
                              </div>
                              <div>
                                <span>Explorer</span>
                                <a href={record.explorerUrl} target="_blank" rel="noreferrer">
                                  Open TestNet explorer
                                </a>
                              </div>
                              <div>
                                <span>Confirmation round</span>
                                <strong>{record.confirmationRound || 'Pending'}</strong>
                              </div>
                              <div>
                                <span>Network fee</span>
                                <strong>{record.feeAlgo} ALGO</strong>
                              </div>
                              <div>
                                <span>Escrow status</span>
                                <strong>{record.escrowStatus}</strong>
                              </div>
                              <div>
                                <span>IPFS CID</span>
                                <a href={record.ipfsUrl} target="_blank" rel="noreferrer">
                                  {record.cid}
                                </a>
                              </div>
                              <div>
                                <span>Content hash</span>
                                <strong>{record.contentHash}</strong>
                              </div>
                              <div>
                                <span>Listing metadata</span>
                                <strong>{record.listingMetadata}</strong>
                              </div>
                              <div>
                                <span>Seller wallet</span>
                                <strong>{record.seller}</strong>
                              </div>
                              <div>
                                <span>Buyer wallet</span>
                                <strong>{record.buyer}</strong>
                              </div>
                              <div>
                                <span>Contract ID</span>
                                <strong>{record.contractId}</strong>
                              </div>
                              <div>
                                <span>Error message</span>
                                <strong>{record.errorMessage || 'None'}</strong>
                              </div>
                            </div>
                            <div className="activity-detail-actions">
                              <button
                                type="button"
                                className="activity-action-btn"
                                onClick={() => handleProofBundleDownload(record)}
                              >
                                Download Proof Bundle
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            {filtered.length === 0 && (
              <div className="activity-empty">
                <h3>No matching transactions found.</h3>
                <p>Adjust search, filters, or sorting to inspect other proof records.</p>
              </div>
            )}
          </article>

          <article className="activity-proof-note">
            <p>
              This ledger is designed as a transparent proof repository: every event links back to
              transaction and content evidence so operators and buyers can audit end-to-end flow.
            </p>
          </article>
        </div>
      </section>
    </div>
  )
}

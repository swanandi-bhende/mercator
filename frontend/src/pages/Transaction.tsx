import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

export default function TransactionPage() {
  const navigate = useNavigate()
  const { paymentState, selectedInsight } = useAppContext()
  const [copied, setCopied] = useState(false)

  const paymentTxId = paymentState?.paymentTxId || paymentState?.txId || ''
  const escrowTxId = paymentState?.escrowTxId || ''
  const cid = paymentState?.ipfsCid || selectedInsight?.cid || ''
  const listingId = paymentState?.listingId || selectedInsight?.listing_id || ''
  const deliveredInsight =
    paymentState?.deliveredInsightText ||
    selectedInsight?.insight_text ||
    'Insight delivery text unavailable.'

  if (!paymentTxId && !listingId && !cid) {
    return (
      <div className="receipt-page">
        <section className="receipt-empty">
          <div className="home-wrap">
            <div className="receipt-empty-card">
              <p className="home-kicker">Receipt / Unlock</p>
              <h1>No completed purchase found.</h1>
              <p>Complete checkout to unlock delivered insight and on-chain proof details.</p>
              <button className="receipt-btn receipt-btn--primary" onClick={() => navigate('/discover')}>
                Back to Discover
              </button>
            </div>
          </div>
        </section>
      </div>
    )
  }

  const paymentExplorerUrl =
    paymentState?.explorerPaymentUrl ||
    (paymentTxId ? `https://explorer.perawallet.app/tx/${paymentTxId}/` : '')
  const escrowExplorerUrl =
    paymentState?.explorerEscrowUrl ||
    (escrowTxId ? `https://explorer.perawallet.app/tx/${escrowTxId}/` : '')
  const ipfsRecordUrl = cid ? `https://ipfs.io/ipfs/${cid}` : ''

  const escrowReleased = paymentState?.escrowReleased ?? Boolean(escrowTxId)

  const timeline = [
    {
      label: 'Payment confirmed',
      done: Boolean(paymentTxId),
      detail: paymentTxId ? 'USDC transfer confirmed on TestNet.' : 'Awaiting payment confirmation.',
    },
    {
      label: 'Escrow locked',
      done: Boolean(paymentTxId),
      detail: paymentTxId
        ? 'Funds were routed through escrow before release.'
        : 'Escrow lock pending payment confirmation.',
    },
    {
      label: 'Insight delivered',
      done: Boolean(deliveredInsight && deliveredInsight !== 'Insight delivery text unavailable.'),
      detail:
        deliveredInsight && deliveredInsight !== 'Insight delivery text unavailable.'
          ? 'IPFS-backed insight content unlocked for buyer.'
          : 'Delivery output pending.',
    },
    {
      label: 'Escrow released',
      done: escrowReleased,
      detail: escrowReleased
        ? 'Escrow released to seller after delivery.'
        : 'Escrow release pending or delayed.',
    },
  ]

  const handleCopyInsight = async () => {
    try {
      await navigator.clipboard.writeText(deliveredInsight)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  const handleCopyPaymentTx = async () => {
    if (!paymentTxId) return
    try {
      await navigator.clipboard.writeText(paymentTxId)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  const handleSaveInsight = () => {
    const content = `Mercator Insight Receipt\n\nListing ID: ${listingId || 'Unavailable'}\nCID: ${cid || 'Unavailable'}\nPayment Tx: ${paymentTxId || 'Unavailable'}\nEscrow Tx: ${escrowTxId || 'Unavailable'}\n\nDelivered Insight:\n${deliveredInsight}\n`
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `mercator-insight-${listingId || 'receipt'}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="receipt-page">
      <section className="receipt-hero">
        <div className="home-wrap receipt-shell">
          <div className="receipt-hero-head">
            <p className="home-kicker">Receipt / Unlock</p>
            <h1>Purchase complete, insight unlocked.</h1>
            <p>
              Mercator confirms payment, escrow outcome, and delivered content in one verifiable
              receipt.
            </p>
            <div className="receipt-hero-icons" aria-hidden="true">
              <span>✓</span>
              <span>🔐</span>
              <span>⛓</span>
              <span>📦</span>
            </div>
          </div>

          <article className="receipt-timeline-card">
            <p className="home-kicker">Purchase Timeline</p>
            <h2>Multi-step flow confirmation</h2>
            <ul className="receipt-timeline-list">
              {timeline.map((step) => (
                <li key={step.label} className={step.done ? 'is-done' : 'is-pending'}>
                  <div>
                    <strong>{step.label}</strong>
                    <span>{step.detail}</span>
                  </div>
                  <em>{step.done ? 'Done' : 'Pending'}</em>
                </li>
              ))}
            </ul>
          </article>

          <article className="receipt-insight-card">
            <p className="home-kicker">Delivered Insight</p>
            <h2>Your purchased market insight</h2>
            <div className="receipt-insight-body">
              <p>{deliveredInsight}</p>
            </div>
            <div className="receipt-inline-actions">
              <button className="receipt-btn receipt-btn--secondary" onClick={handleCopyInsight}>
                {copied ? 'Copied' : 'Copy Insight'}
              </button>
              <button className="receipt-btn receipt-btn--secondary" onClick={handleSaveInsight}>
                Save Locally
              </button>
            </div>
          </article>

          <article className="receipt-proof-card">
            <p className="home-kicker">Transaction Summary</p>
            <h2>On-chain proof elements</h2>
            <div className="receipt-proof-grid">
              <div>
                <span>Payment tx ID</span>
                <strong>{paymentTxId || 'Unavailable'}</strong>
                {paymentExplorerUrl && (
                  <a href={paymentExplorerUrl} target="_blank" rel="noreferrer">
                    View payment on explorer
                  </a>
                )}
              </div>
              <div>
                <span>Escrow release tx ID</span>
                <strong>{escrowTxId || 'Unavailable / delayed'}</strong>
                {escrowExplorerUrl && (
                  <a href={escrowExplorerUrl} target="_blank" rel="noreferrer">
                    View escrow release on explorer
                  </a>
                )}
              </div>
              <div>
                <span>IPFS CID</span>
                <strong>{cid || 'Unavailable'}</strong>
                {ipfsRecordUrl && (
                  <a href={ipfsRecordUrl} target="_blank" rel="noreferrer">
                    Open IPFS record
                  </a>
                )}
              </div>
              <div>
                <span>Listing ID</span>
                <strong>{listingId || 'Unavailable'}</strong>
              </div>
              <div>
                <span>Payment confirmation</span>
                <strong>{paymentTxId ? 'Confirmed' : 'Not confirmed'}</strong>
              </div>
              <div>
                <span>Escrow confirmation</span>
                <strong>{escrowReleased ? 'Released to seller' : 'Pending or failed'}</strong>
              </div>
            </div>
          </article>

          <article className="receipt-trust-card">
            <p className="home-kicker">Trust & Verification</p>
            <h2>What just happened</h2>
            <ul>
              <li>Escrow held payment during fulfillment to protect buyer and seller incentives.</li>
              <li>Insight content is tied to an IPFS CID for integrity and retrieval proof.</li>
              <li>Payment and escrow transactions are traceable on-chain through explorer links.</li>
              <li>Listing ID, CID, and tx records create an auditable marketplace trail.</li>
            </ul>
          </article>

          <article className={`receipt-escrow-card ${escrowReleased ? 'is-success' : 'is-pending'}`}>
            <p className="home-kicker">Escrow Status</p>
            <h2>{escrowReleased ? 'Escrow released to seller' : 'Escrow release pending review'}</h2>
            <p>
              {escrowReleased
                ? 'Payment was held by escrow and released after delivery confirmation, protecting both buyer and seller.'
                : 'Payment is confirmed but escrow release has not been fully confirmed yet. Check explorer links and activity logs.'}
            </p>
          </article>

          <div className="receipt-actions">
            <button className="receipt-btn receipt-btn--primary" onClick={() => navigate('/activity')}>
              View Full Activity Log
            </button>
            <button
              className="receipt-btn receipt-btn--secondary"
              onClick={handleCopyPaymentTx}
              disabled={!paymentTxId}
            >
              {copied ? 'Copied' : 'Copy Payment Tx ID'}
            </button>
            <button
              className="receipt-btn receipt-btn--secondary"
              onClick={() => paymentExplorerUrl && window.open(paymentExplorerUrl, '_blank', 'noreferrer')}
              disabled={!paymentExplorerUrl}
            >
              Verify Payment Tx
            </button>
            <button
              className="receipt-btn receipt-btn--secondary"
              onClick={() => escrowExplorerUrl && window.open(escrowExplorerUrl, '_blank', 'noreferrer')}
              disabled={!escrowExplorerUrl}
            >
              Verify Escrow Tx
            </button>
            <button className="receipt-btn receipt-btn--secondary" onClick={() => navigate('/discover')}>
              Find More Insights
            </button>
            <button className="receipt-btn receipt-btn--secondary" onClick={() => navigate('/discover')}>
              Explore Seller Listings
            </button>
            <button className="receipt-btn receipt-btn--secondary" onClick={() => navigate('/sell')}>
              Create Another Listing
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

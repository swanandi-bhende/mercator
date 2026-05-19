import { useMemo, useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { SellerCard } from '../components/SellerCard'
import ExpiryCountdown from '../components/ExpiryCountdown'
import '../styles/listing.css'
import useWebSocket, { WebSocketEvent } from '../hooks/useWebSocket'

type TrustBand = 'trusted' | 'borderline' | 'below'
type ValueBand = 'cheap' | 'fair' | 'expensive'

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export default function InsightDetailPage() {
  const navigate = useNavigate()
  const { selectedInsight, sellerMetadata, setHasReviewedEvaluation } = useAppContext()

  // Define handlers early to avoid initialization errors in early returns
  const handleBuyNow = () => {
    setHasReviewedEvaluation(true)
    navigate('/checkout')
  }

  const copyIpfsCid = async (ipfsCid: string) => {
    if (!ipfsCid) return

    try {
      await navigator.clipboard.writeText(ipfsCid)
    } catch {
      // Clipboard access is best effort.
    }
  }

  // Agent evaluation panel state
  const [agentEvaluation, setAgentEvaluation] = useState<null | {
    listing_id: string
    total_score: number
    buy_confidence: number
    decision: string
    decision_reasoning: string
    improvement_suggestion?: string
    step_scores?: number[]
    step_evidence?: string[]
  }>(
    selectedInsight && (selectedInsight as any).evaluation
      ? (selectedInsight as any).evaluation
      : null
  )
  const [showAboutSeller, setShowAboutSeller] = useState(false)
  const [currentRound, setCurrentRound] = useState<number>(0)
  const [isExpiredVisual, setIsExpiredVisual] = useState(false)

  useWebSocket((event: WebSocketEvent) => {
    try {
      if (event.event_type === 'agent_evaluation_completed') {
        const payload = event.payload as any
        if (!selectedInsight) return
        if (String(payload.listing_id) === String(selectedInsight.listing_id)) {
          setAgentEvaluation({
            listing_id: String(payload.listing_id),
            total_score: Number(payload.total_score || 0),
            buy_confidence: Number(payload.buy_confidence || 0),
            decision: String(payload.decision || 'SKIP'),
            decision_reasoning: String(payload.decision_reasoning || ''),
            improvement_suggestion: String(payload.improvement_suggestion || ''),
            step_scores: Array.isArray(payload.step_scores) ? payload.step_scores as number[] : [],
          })
        }
      }
      if (event.event_type === 'health_update') {
        const payload = event.payload as any
        const round = Number(payload.current_round || payload.last_round || 0)
        if (round && round > 0) setCurrentRound(round)
      }
    } catch (err) {
      // ignore malformed ws payloads
    }
  })

  if (!selectedInsight) {
    return (
      <div className="insight-decision-page">
        <section className="insight-decision-empty">
          <div className="home-wrap">
            <div className="insight-decision-empty-card">
              <p className="home-kicker">Decision Screen</p>
              <h1>No insight selected yet.</h1>
              <p>
                Choose an insight from Discover to review relevance, trust, and value before you
                decide to buy.
              </p>
              <button
                onClick={() => navigate('/discover')}
                className="insight-decision-btn insight-decision-btn--primary"
              >
                Back to Discover
              </button>
              <button
                onClick={() => navigate('/trust')}
                className="insight-decision-btn insight-decision-btn--secondary"
              >
                Trust / Reputation Guide
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  const queryText = selectedInsight.query_text?.trim() || 'your latest market query'
  const relevanceScore = clamp(Math.round(selectedInsight.relevance_score ?? 76), 1, 99)
  const reputation = Math.round(sellerMetadata?.reputation ?? selectedInsight.seller_reputation ?? 0)
  const price = selectedInsight.price

  const trustBand: TrustBand =
    reputation >= 70 ? 'trusted' : reputation >= 50 ? 'borderline' : 'below'

  const trustLabel =
    trustBand === 'trusted'
      ? 'Trusted seller'
      : trustBand === 'borderline'
        ? 'Borderline trust'
        : 'Below trust threshold'

  const trustConsequence =
    trustBand === 'trusted'
      ? 'Seller is above threshold. Trust checks pass for normal flow.'
      : trustBand === 'borderline'
        ? 'Seller is near threshold. Review rationale and price before purchase.'
        : 'Seller is below threshold. Buyer risk is elevated and purchase may be skipped by policy.'

  const valueIndex = price > 0 ? relevanceScore / price : 0
  const valueBand: ValueBand = valueIndex >= 60 ? 'cheap' : valueIndex >= 35 ? 'fair' : 'expensive'
  const valueLabel =
    valueBand === 'cheap' ? 'Cheap for signal quality' : valueBand === 'fair' ? 'Fairly priced' : 'Expensive for quality'

  const recommendation = useMemo(() => {
    if (trustBand === 'below') {
      return {
        title: 'Hold purchase unless you need this specific edge right now.',
        body: 'Trust is below threshold, which weakens confidence despite topical match.',
        tone: 'risk',
      }
    }

    if (relevanceScore >= 75 && valueBand !== 'expensive') {
      return {
        title: 'Worth buying now.',
        body: 'Strong semantic fit with acceptable trust and price positioning.',
        tone: 'go',
      }
    }

    return {
      title: 'Review carefully before buying.',
      body: 'Signal quality is mixed, so compare alternatives before checkout.',
      tone: 'caution',
    }
  }, [relevanceScore, trustBand, valueBand])

  const synopsis =
    selectedInsight.synopsis ||
    sellerMetadata?.rankingReason ||
    'This listing appears in your shortlist due to semantic query overlap and current relevance signals.'

  const marketContext = selectedInsight.market_context || 'General market context'
  const sellerIdentity = sellerMetadata?.address || selectedInsight.seller_wallet
  const listingStatus = sellerMetadata?.listingStatus || 'Active'
  const listingState = (selectedInsight.state || selectedInsight.listing_status || listingStatus || 'active').toLowerCase()
  const expiryRound = Number(selectedInsight.expiry_round || sellerMetadata?.expiry_round || 0)
  const ipfsCid = String(selectedInsight.cid || '').trim()
  const [ipfsContent, setIpfsContent] = useState<string | null>(null)
  const [ipfsLoading, setIpfsLoading] = useState(false)
  const [ipfsError, setIpfsError] = useState<string | null>(null)

  const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
  const ipfsPreviewUrl = ipfsCid ? `${apiBase}/api/v1/ipfs/${encodeURIComponent(ipfsCid)}` : ''

  useEffect(() => {
    let cancelled = false
    if (!ipfsCid) return
    setIpfsLoading(true)
    setIpfsError(null)
    setIpfsContent(null)

    void (async () => {
      try {
        const url = ipfsPreviewUrl
        const resp = await fetch(url, { method: 'GET' })
        if (!resp.ok) throw new Error(`Failed to fetch IPFS preview: ${resp.status}`)
        const data = await resp.json()
        if (cancelled) return
        if (data && data.success && typeof data.content === 'string') setIpfsContent(data.content)
        else throw new Error(data?.message || 'No content returned')
      } catch (err: any) {
        if (cancelled) return
        setIpfsError(String(err?.message || err))
      } finally {
        if (!cancelled) setIpfsLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [ipfsCid, ipfsPreviewUrl])

  const rationaleLines = [
    `Relevance scored ${relevanceScore}% against your query intent.`,
    `Seller reputation is ${reputation}/100 (${trustLabel.toLowerCase()}).`,
    `Price is ${price} USDC with a value index of ${valueIndex.toFixed(1)} points per USDC.`,
    recommendation.tone === 'go'
      ? 'Combined signals support a BUY path.'
      : recommendation.tone === 'caution'
        ? 'Signals are mixed, so a compare-and-refine path is safer.'
        : 'Trust policy risk is high, so a SKIP path is recommended.',
  ]

  const improvementSuggestions = [
    'Use a narrower market prompt with symbol + timeframe.',
    'Prefer sellers above 70 reputation for lower risk decisions.',
    'Target value index above 35 before checkout.',
  ]

  const shouldShowRiskRecovery = recommendation.tone !== 'go'

  return (
    <div className="insight-decision-page">
      <section className="insight-decision-hero">
        <div className="home-wrap insight-decision-layout">
          <article className={`insight-focus-card ${listingState === 'expired' || isExpiredVisual ? 'listing-expired' : listingState === 'sold' ? 'listing-sold' : ''}`}>
            <p className="home-kicker">Decision Screen</p>
            <h1>Is this insight worth buying right now?</h1>

                <div className={`insight-summary-head`}>
              <h2>{selectedInsight.insight_text}</h2>
              <p>{synopsis}</p>
                  <div style={{ marginTop: 8 }} className={`${listingState === 'expired' || isExpiredVisual ? 'listing-expired' : listingState === 'sold' ? 'listing-sold' : ''}`}>
                <span className={`insight-state-pill insight-state-pill--${listingState}`}>{listingState.toUpperCase()}</span>
                {listingState === 'active' && (
                  <div style={{ float: 'right' }}>
                    <ExpiryCountdown expiry_round={expiryRound} current_round={currentRound} state={listingState} onExpired={() => { setIsExpiredVisual(true) }} />
                  </div>
                )}
                {listingState === 'sold' && <div>Sold at round {selectedInsight.sold_at_round || 'N/A'} to {selectedInsight.buyer_wallet || 'unknown'}</div>}
                {listingState === 'expired' && <div>Expired at round {selectedInsight.expired_at_round || 'N/A'}</div>}
                {listingState === 'active' && expiryRound && currentRound && ((expiryRound - currentRound) * 4.5) <= 30 * 60 && (
                  <div className="insight-urgency">Purchase before expiry</div>
                )}
              </div>
            </div>

            <div className="insight-anchor-grid">
              <div>
                <span>Market context</span>
                <strong>{marketContext}</strong>
              </div>
              <div>
                <span>Seller identity</span>
                <strong>{sellerIdentity}</strong>
              </div>
              <div>
                <span>Your query</span>
                <strong>{queryText}</strong>
              </div>
            </div>

            <div className="insight-ipfs-panel">
              <div className="insight-ipfs-header">
                <div>
                  <p className="home-kicker">IPFS Preview</p>
                  <h2>View the content exactly as pinned by the seller.</h2>
                </div>
                <span className={`insight-state-pill insight-state-pill--${ipfsCid ? 'active' : 'expired'}`}>
                  {ipfsCid ? 'CID available' : 'CID unavailable'}
                </span>
              </div>

              {ipfsCid ? (
                <div className="insight-ipfs-frame" style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', padding: 12, background: '#fff' }}>
                  {ipfsLoading && <div>Loading IPFS preview…</div>}
                  {ipfsError && (
                    <div>
                      <h3>IPFS preview unavailable</h3>
                      <p className="muted">{ipfsError}</p>
                      <p>Open the raw record in a new tab using the link below.</p>
                    </div>
                  )}
                  {ipfsContent && <div>{ipfsContent}</div>}
                </div>
              ) : (
                <div className="insight-ipfs-empty">
                  <h3>No IPFS preview is available yet.</h3>
                  <p>The listing is still readable, but the CID has not been surfaced for inline preview.</p>
                </div>
              )}

              <div className="insight-ipfs-meta">
                <div>
                  <span>CID</span>
                  <strong>{ipfsCid || 'Unavailable'}</strong>
                </div>
                <div>
                  <span>Preview link</span>
                  <strong>{ipfsPreviewUrl || 'Unavailable'}</strong>
                </div>
              </div>

              <div className="insight-ipfs-actions">
                {ipfsPreviewUrl ? (
                  <a href={ipfsPreviewUrl} target="_blank" rel="noreferrer" className="insight-ipfs-link">
                    Open IPFS
                  </a>
                ) : (
                  <span className="insight-ipfs-link is-disabled">Open IPFS</span>
                )}
                <button type="button" onClick={() => copyIpfsCid(ipfsCid)} className="insight-ipfs-copy">
                  Copy CID
                </button>
              </div>
            </div>
          </article>

          <aside className="insight-recommendation-card">
            <p className="home-kicker">Recommendation</p>
            <h3>{recommendation.title}</h3>
            <p>{recommendation.body}</p>
            <p className={`insight-tone-chip ${recommendation.tone}`}>
              {recommendation.tone === 'go'
                ? 'Buy signal is positive'
                : recommendation.tone === 'caution'
                  ? 'Decision needs caution'
                  : 'High trust risk detected'}
            </p>
          </aside>

          <aside className="insight-seller-card">
            <button
              className="insight-seller-toggle"
              onClick={() => setShowAboutSeller(!showAboutSeller)}
            >
              <p className="home-kicker">About this Seller</p>
              <span className="toggle-icon">{showAboutSeller ? '▼' : '▶'}</span>
            </button>
            {showAboutSeller && sellerIdentity && (
              <div className="insight-seller-expanded">
                <SellerCard wallet={sellerIdentity} expanded={true} />
              </div>
            )}
          </aside>
        </div>
      </section>

      <section className="insight-decision-panels">
        <div className="home-wrap insight-panels-grid">
          <article className="insight-panel">
            <p className="home-kicker">Relevance</p>
            <h3>{relevanceScore}% semantic fit</h3>
            <div className="insight-meter" role="img" aria-label={`Relevance score ${relevanceScore} percent`}>
              <span style={{ width: `${relevanceScore}%` }} />
            </div>
            <p>
              Mercator matched this insight to "{queryText}" using semantic overlap and market-intent
              alignment.
            </p>
          </article>

          <article className="insight-panel">
            <p className="home-kicker">Trust Layer</p>
            <h3>{trustLabel}</h3>
            <div className={`insight-badge insight-badge--${trustBand}`}>Reputation {reputation} / 100</div>
            <p>{trustConsequence}</p>
            <small>
              Threshold logic: trusted &gt;= 70, borderline 50-69, below threshold &lt; 50.
            </small>
          </article>

          <article className="insight-panel">
            <p className="home-kicker">Value vs Price</p>
            <h3>{price} USDC</h3>
            <div className={`insight-badge insight-badge--${valueBand}`}>{valueLabel}</div>
            <p>
              Why this price makes sense: relevance ({relevanceScore}) and trust ({reputation})
              jointly imply a value index of {valueIndex.toFixed(1)} points per USDC.
            </p>
          </article>
        </div>
      </section>

      <section className="insight-rationale-section">
        <div className="home-wrap insight-rationale-grid">
          <article className="insight-panel insight-rationale-card">
            <p className="home-kicker">Decision Rationale</p>
            <h3>Agent-style reasoning summary</h3>
            <ul className="insight-rationale-list">
              {rationaleLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>

            {shouldShowRiskRecovery && (
              <div className="insight-recovery-block">
                <h4>Why this is currently not a strong buy</h4>
                <div className="insight-rejected-metrics">
                  <div>
                    <span>Relevance</span>
                    <strong>{relevanceScore}%</strong>
                  </div>
                  <div>
                    <span>Reputation</span>
                    <strong>{reputation}/100</strong>
                  </div>
                  <div>
                    <span>Value Index</span>
                    <strong>{valueIndex.toFixed(1)}</strong>
                  </div>
                </div>
                <ul className="insight-recovery-list">
                  {improvementSuggestions.map((suggestion) => (
                    <li key={suggestion}>{suggestion}</li>
                  ))}
                </ul>
              </div>
            )}
          </article>

          <article className="insight-panel insight-proof-card">
            <p className="home-kicker">Verification</p>
            <h3>Backend-linked proof elements</h3>
            <div className="insight-proof-grid">
              <div>
                <span>Listing ID</span>
                <strong>{selectedInsight.listing_id || 'Unavailable'}</strong>
              </div>
              <div>
                <span>CID</span>
                <strong>{selectedInsight.cid || 'Unavailable'}</strong>
              </div>
              <div>
                <span>Transaction</span>
                <strong>{selectedInsight.tx_id || 'Pending reveal'}</strong>
              </div>
              <div>
                <span>ASA ID</span>
                <strong>{selectedInsight.asa_id || 'Unavailable'}</strong>
              </div>
              <div>
                <span>Listing status</span>
                <strong>{listingStatus}</strong>
              </div>
              <div>
                <span>Seller wallet</span>
                <strong>{sellerIdentity}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="insight-evaluation-section">
        <div className="home-wrap insight-evaluation-panel">
          <article className="insight-panel">
            <p className="home-kicker">Agent Reasoning</p>
            {!agentEvaluation ? (
              <div>
                <h3>Evaluation pending</h3>
                <p className="muted">The buyer agent is evaluating this listing. Results will appear here when available.</p>
              </div>
            ) : (
              <div>
                <h3>{agentEvaluation.decision === 'BUY' ? 'BUY ✓' : 'SKIP ✗'}</h3>
                <div className="evaluation-summary">
                  <div className={`evaluation-badge ${agentEvaluation.buy_confidence >= 75 ? 'green' : 'red'}`}>
                    {agentEvaluation.buy_confidence}%
                  </div>
                  <div className="evaluation-details">
                    <p className="evaluation-reason">{agentEvaluation.decision_reasoning}</p>
                    {agentEvaluation.decision === 'SKIP' && agentEvaluation.improvement_suggestion && (
                      <div className="improvement-box">
                        <strong>What would make this worth buying?</strong>
                        <p>{agentEvaluation.improvement_suggestion}</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="evaluation-criteria-grid">
                  <div className="criteria-card">
                    <strong>Relevance</strong>
                    <div className="criteria-score">{agentEvaluation.step_scores?.[0] || 0} / 40</div>
                  </div>
                  <div className="criteria-card">
                    <strong>Reputation</strong>
                    <div className="criteria-score">{agentEvaluation.step_scores?.[1] || 0} / 20</div>
                  </div>
                  <div className="criteria-card">
                    <strong>Value</strong>
                    <div className="criteria-score">{agentEvaluation.step_scores?.[2] || 0} / 20</div>
                  </div>
                  <div className="criteria-card">
                    <strong>Specificity</strong>
                    <div className="criteria-score">{agentEvaluation.step_scores?.[3] || 0} / 20</div>
                  </div>
                </div>

                <div className="evaluation-total">
                  <strong>Total</strong>
                  <div className="total-score">{agentEvaluation.total_score} / 100</div>
                </div>
              </div>
            )}
          </article>
        </div>
      </section>

      <section className="insight-decision-actions">
        <div className="home-wrap insight-actions-wrap">
          {recommendation.tone === 'go' ? (
            <>
              <button
                onClick={handleBuyNow}
                className="insight-decision-btn insight-decision-btn--primary"
              >
                Buy This Insight
              </button>
              <button
                onClick={() => navigate('/trust')}
                className="insight-decision-btn insight-decision-btn--secondary"
              >
                Trust / Reputation Guide
              </button>
              <button
                onClick={() => navigate('/discover')}
                className="insight-decision-btn insight-decision-btn--secondary"
              >
                Compare More Insights
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleBuyNow}
                className="insight-decision-btn insight-decision-btn--primary"
              >
                Buy Anyway
              </button>
              <button
                onClick={() => navigate('/trust')}
                className="insight-decision-btn insight-decision-btn--secondary"
              >
                Inspect Seller Trust Rules
              </button>
            </>
          )}
          <p>
            Next step is explicit: {recommendation.tone === 'go' ? 'approve this path and move to checkout, or compare alternatives.' : 'refine the query or inspect trust policy before retrying.'}{' '}
            <button className="insight-link" onClick={() => navigate('/trust')}>Review trust logic and ranking rules.</button>
          </p>
        </div>
      </section>
    </div>
  )
}

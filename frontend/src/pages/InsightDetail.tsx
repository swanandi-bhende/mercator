import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

type TrustBand = 'trusted' | 'borderline' | 'below'
type ValueBand = 'cheap' | 'fair' | 'expensive'

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export default function InsightDetailPage() {
  const navigate = useNavigate()
  const { selectedInsight, sellerMetadata, setHasReviewedEvaluation } = useAppContext()

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
            </div>
          </div>
        </section>
      </div>
    )
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

  const handleContinueToCheckout = () => {
    setHasReviewedEvaluation(true)
    navigate('/checkout')
  }

  return (
    <div className="insight-decision-page">
      <section className="insight-decision-hero">
        <div className="home-wrap insight-decision-layout">
          <article className="insight-focus-card">
            <p className="home-kicker">Decision Screen</p>
            <h1>Is this insight worth buying right now?</h1>

            <div className="insight-summary-head">
              <h2>{selectedInsight.insight_text}</h2>
              <p>{synopsis}</p>
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

      <section className="insight-decision-actions">
        <div className="home-wrap insight-actions-wrap">
          {recommendation.tone === 'go' ? (
            <>
              <button
                onClick={handleContinueToCheckout}
                className="insight-decision-btn insight-decision-btn--primary"
              >
                Continue to Checkout
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
                onClick={() => navigate('/discover')}
                className="insight-decision-btn insight-decision-btn--primary"
              >
                Refine Query in Discover
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
            <a href="/trust">Review trust logic and ranking rules.</a>
          </p>
        </div>
      </section>
    </div>
  )
}

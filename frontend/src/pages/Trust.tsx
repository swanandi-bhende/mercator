import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

type TrustBand = 'trusted' | 'borderline' | 'below' | 'unknown'
type TrustDecision = 'accepted' | 'skipped'

function getTrustBand(score: number | null): TrustBand {
  if (score === null) return 'unknown'
  if (score >= 50) return 'trusted'
  if (score >= 40) return 'borderline'
  return 'below'
}

export default function TrustPage() {
  const navigate = useNavigate()
  const { selectedInsight, sellerMetadata, paymentState } = useAppContext()

  const sellerScore = useMemo(() => {
    const byMetadata = sellerMetadata?.reputation
    const byInsight = selectedInsight?.seller_reputation
    const value = byMetadata ?? byInsight
    return typeof value === 'number' ? Math.max(0, Math.min(100, Math.round(value))) : null
  }, [sellerMetadata, selectedInsight])

  const sellerAddress = sellerMetadata?.address || selectedInsight?.seller_wallet || 'No seller selected'
  const trustBand = getTrustBand(sellerScore)

  const trustLabel =
    trustBand === 'trusted'
      ? 'Trusted (50+)'
      : trustBand === 'borderline'
        ? 'Borderline (40-49, below threshold)'
        : trustBand === 'below'
          ? 'Below threshold (<40)'
          : 'No score context yet'

  const trustSummary =
    trustBand === 'trusted'
      ? 'Seller can be evaluated for purchase because score is at or above threshold.'
      : trustBand === 'borderline'
        ? 'Seller has some positive history, but still fails the 50+ rule and is auto-skipped.'
        : trustBand === 'below'
          ? 'Seller is below trust threshold and will be auto-skipped to protect the buyer.'
          : 'Run discovery or evaluation to load seller-specific trust context.'

  const scoreWidth = `${sellerScore ?? 0}%`

  const reputationJourney = [
    {
      title: 'New seller with no history',
      score: 18,
      story:
        'A new seller has listed insights but has not yet proven delivery consistency. The agent keeps the seller below threshold until reliable outcomes are observed.',
      outcome: 'Likely skipped until trust is earned through successful, verified sales.',
    },
    {
      title: 'Consistent five-star seller',
      score: 86,
      story:
        'This seller repeatedly delivers accurate, useful insights and confirms fulfillment cleanly. Their score stays well above threshold and is trusted by default.',
      outcome: 'Accepted for evaluation, with higher buyer confidence and smoother conversion.',
    },
    {
      title: 'Seller with delivery problems',
      score: 34,
      story:
        'A seller had failed fulfillment events and inconsistent quality. Reputation dropped below the trust gate and now blocks automatic buy paths.',
      outcome: 'Skipped by policy, even if relevance appears strong.',
    },
    {
      title: 'Seller rebuilding trust',
      score: 47,
      story:
        'After improving quality and consistency, this seller is climbing back. The score shows progress but remains below the 50 trust threshold.',
      outcome: 'Visible to buyers, but still skipped until crossing 50+.',
    },
  ]

  const faqItems = [
    {
      q: 'Can I still see insights from low-reputation sellers?',
      a: 'Yes. Mercator can show them for transparency, but the agent auto-skips purchase when seller reputation is below 50.',
    },
    {
      q: 'Can a seller improve their reputation?',
      a: 'Yes. Reputation is dynamic and increases through successful sales, consistent quality, and trustworthy fulfillment behavior.',
    },
    {
      q: 'How long does it take to build trust?',
      a: 'There is no fixed timeline. Trust builds over repeated successful outcomes and can decline when fulfillment or quality slips.',
    },
  ]

  const decisionFeed = useMemo(() => {
    const items: {
      id: string
      insight: string
      seller: string
      score: number
      decision: TrustDecision
      reason: string
      tag: string
    }[] = []

    if (selectedInsight && sellerScore !== null) {
      const decision: TrustDecision = sellerScore >= 50 ? 'accepted' : 'skipped'
      items.push({
        id: 'live-context',
        insight: selectedInsight.insight_text,
        seller: sellerAddress,
        score: sellerScore,
        decision,
        reason:
          decision === 'accepted'
            ? 'Accepted because reputation met the 50+ trust threshold.'
            : 'Skipped because reputation was below the 50 trust threshold.',
        tag: 'Current context',
      })
    }

    items.push(
      {
        id: 'recent-1',
        insight: 'NIFTY intraday momentum continuation',
        seller: 'ALGO...8X2A',
        score: 82,
        decision: 'accepted',
        reason: 'Accepted after passing relevance, value, and reputation checks.',
        tag: 'Recent decision',
      },
      {
        id: 'recent-2',
        insight: 'High-risk small-cap reversal rumor',
        seller: 'ALGO...Q19P',
        score: 36,
        decision: 'skipped',
        reason: 'Skipped due to low-reputation protection despite topical relevance.',
        tag: 'Recent decision',
      },
      {
        id: 'recent-3',
        insight: 'BankNifty options hedge setup',
        seller: 'ALGO...M77K',
        score: 49,
        decision: 'skipped',
        reason: 'Skipped because borderline score is still below threshold.',
        tag: 'Recent decision',
      },
    )

    return items.slice(0, 4)
  }, [selectedInsight, sellerScore, sellerAddress])

  return (
    <div className="trust-page">
      <section className="trust-hero">
        <div className="home-wrap trust-shell">
          <article className="trust-head-card">
            <p className="home-kicker">Trust / Reputation</p>
            <h1>Mercator credibility is a product rule, not a cosmetic label.</h1>
            <p>
              Reputation is a hard decision input in the agent flow. It determines whether a
              listing is eligible for purchase, protects buyers from weak sellers, and rewards
              consistent seller quality.
            </p>
          </article>

          <article className="trust-threshold-card">
            <p className="home-kicker">Threshold Rule</p>
            <h2>Score 50 or above is required for trust.</h2>
            <ul>
              <li>50+ reputation: seller is considered trustworthy for automated evaluation.</li>
              <li>Below 50 reputation: agent skips purchase automatically, even if relevance is high.</li>
              <li>This behavior is deterministic and applied consistently across all insights.</li>
            </ul>
          </article>

          <article className={`trust-score-card is-${trustBand}`}>
            <p className="home-kicker">Current Seller Reputation</p>
            <h2>Live score from active insight context</h2>

            <div className="trust-score-head">
              <strong>{sellerScore !== null ? `${sellerScore}/100` : 'Unavailable'}</strong>
              <span>{trustLabel}</span>
            </div>

            <div className="trust-score-meter" aria-hidden="true">
              <div className="trust-score-fill" style={{ width: scoreWidth }} />
            </div>

            <p className="trust-score-copy">{trustSummary}</p>
            <small>Seller: {sellerAddress}</small>

            <div className="trust-legend">
              <span className="is-green">50+ Trusted</span>
              <span className="is-yellow">40-49 Borderline</span>
              <span className="is-red">0-39 Below threshold</span>
            </div>
          </article>

          <article className="trust-factors-card">
            <p className="home-kicker">What Affects Reputation</p>
            <h2>How score is earned and lost</h2>
            <ul>
              <li>Successful sales and confirmed fulfillment improve seller credibility.</li>
              <li>Honesty and consistency in delivered insights maintain long-term trust.</li>
              <li>Failed deliveries, misleading outputs, or repeated disputes reduce confidence.</li>
              <li>Low reputation means previous outcomes showed reliability concerns.</li>
            </ul>
          </article>

          <article className="trust-skip-card">
            <p className="home-kicker">Buyer Protection Feature</p>
            <h2>Low-reputation skip is a safety mechanism.</h2>
            <p>
              Mercator treats low-score auto-skip as proactive buyer protection, not a restriction.
              Even when an insight appears relevant, the agent blocks purchase when seller
              reputation is below 50 so buyers are not exposed to untrustworthy sources.
            </p>
          </article>

          <article className="trust-logic-card">
            <p className="home-kicker">Core Product Logic</p>
            <h2>How trust participates in every decision</h2>
            <ol>
              <li>Agent measures query relevance and expected value.</li>
              <li>Agent checks seller reputation threshold (must be 50+).</li>
              <li>If score is below threshold, purchase is skipped automatically.</li>
              <li>If score is valid, buyer proceeds to evaluation and checkout flow.</li>
            </ol>
          </article>

          <section className="trust-edu-grid" aria-label="Reputation education">
            <article className="trust-journey-card">
              <p className="home-kicker">Reputation Journey</p>
              <h2>How seller trust evolves over time</h2>
              <div className="trust-journey-list">
                {reputationJourney.map((item) => {
                  const band = getTrustBand(item.score)
                  return (
                    <article key={item.title} className={`trust-journey-item is-${band}`}>
                      <header>
                        <h3>{item.title}</h3>
                        <span>{item.score}/100</span>
                      </header>
                      <p>{item.story}</p>
                      <small>{item.outcome}</small>
                    </article>
                  )
                })}
              </div>
            </article>

            <article className="trust-feed-card">
              <p className="home-kicker">Reputation In Action</p>
              <h2>Recent acceptance and skip decisions</h2>
              <p className="trust-feed-note">
                Live context is shown when available, alongside recent policy examples.
              </p>
              <div className="trust-feed-list">
                {decisionFeed.map((item) => (
                  <article key={item.id} className="trust-feed-item">
                    <div className="trust-feed-head">
                      <span>{item.tag}</span>
                      <em className={`is-${item.decision}`}>{item.decision === 'accepted' ? 'Accepted' : 'Skipped'}</em>
                    </div>
                    <h3>{item.insight}</h3>
                    <p>{item.reason}</p>
                    <small>
                      Seller {item.seller} • Reputation {item.score}/100
                    </small>
                  </article>
                ))}
              </div>
            </article>
          </section>

          <section className="trust-principles-grid" aria-label="Reputation FAQ and principles">
            <article className="trust-faq-card">
              <p className="home-kicker">Reputation FAQ</p>
              <h2>Fair, transparent, and recoverable trust rules</h2>
              <div className="trust-faq-list">
                {faqItems.map((item) => (
                  <article key={item.q}>
                    <h3>{item.q}</h3>
                    <p>{item.a}</p>
                  </article>
                ))}
              </div>
            </article>

            <article className="trust-principles-card">
              <p className="home-kicker">Trust Principles</p>
              <h2>What Mercator commits to</h2>
              <ul>
                <li>
                  <strong>Transparent:</strong> Reputation thresholds are explicit and visible in
                  the buyer journey.
                </li>
                <li>
                  <strong>Protective:</strong> Low-reputation auto-skip prevents accidental exposure
                  to unreliable sellers.
                </li>
                <li>
                  <strong>Recoverable:</strong> Sellers can rebuild trust through consistent,
                  verifiable fulfillment.
                </li>
                <li>
                  <strong>Actionable:</strong> Trust status influences ranking, evaluation, and
                  purchase flow decisions.
                </li>
              </ul>
            </article>
          </section>

          <div className="trust-actions">
            <button className="trust-btn trust-btn--primary" onClick={() => navigate('/discover')}>
              Back to Discovery
            </button>
            <button className="trust-btn trust-btn--secondary" onClick={() => navigate('/evaluate')}>
              Return to Evaluation
            </button>
            <button className="trust-btn trust-btn--secondary" onClick={() => navigate('/activity')}>
              View Audit Activity
            </button>
            {paymentState?.stage === 'completed' && (
              <button className="trust-btn trust-btn--secondary" onClick={() => navigate('/transaction')}>
                Open Receipt / Unlock
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

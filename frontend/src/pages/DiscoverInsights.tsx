import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { api, ApiError } from '../utils/api'
import type { DiscoverMatch } from '../types'

type SearchPhase = 'idle' | 'fetching' | 'evaluating' | 'ready'
type BackendStatus = 'unknown' | 'online' | 'offline'

type RankedInsight = {
  id: string
  title: string
  seller: string
  wallet: string
  price: number
  reputation: number
  relevance: number
  reason: string
  category: string
  recency: string
  listingStatus: string
  riskSignal: string
  txId: string
  cid: string
  listingId: string
  asaId: string
}

const DEMO_INSIGHTS: RankedInsight[] = [
  {
    id: 'demo-1',
    title: 'NIFTY expected to test 24500 resistance today',
    seller: 'Market Analyst Pro',
    wallet: 'MKT...PRO1',
    price: 2.5,
    reputation: 87,
    relevance: 95,
    reason: 'Strong topical fit, high trust score, and reasonable value.',
    category: 'Indices',
    recency: '2h ago',
    listingStatus: 'Demo',
    riskSignal: 'Low risk',
    txId: 'N/A',
    cid: 'demo-cid-1',
    listingId: 'D-1',
    asaId: '0',
  },
  {
    id: 'demo-2',
    title: 'Best short-term bank index setup this session',
    seller: 'Equity Research Lab',
    wallet: 'EQL...LAB7',
    price: 1.5,
    reputation: 72,
    relevance: 81,
    reason: 'Good thematic overlap but weaker trust profile than top options.',
    category: 'Banking',
    recency: '5h ago',
    listingStatus: 'Demo',
    riskSignal: 'Medium risk',
    txId: 'N/A',
    cid: 'demo-cid-2',
    listingId: 'D-2',
    asaId: '0',
  },
]

function summarizeReason(match: DiscoverMatch, relevance: number, query: string) {
  const reasons: string[] = []

  if (relevance >= 85) {
    reasons.push('high topical match')
  } else if (relevance >= 70) {
    reasons.push('solid topical match')
  } else {
    reasons.push('weaker topical match')
  }

  if (match.reputation >= 85) {
    reasons.push('strong reputation')
  } else if (match.reputation >= 70) {
    reasons.push('acceptable trust signal')
  } else {
    reasons.push('weaker trust signal')
  }

  if (match.price_usdc <= 2) {
    reasons.push('fair price')
  } else {
    reasons.push('higher price for this query')
  }

  if (query.toLowerCase().includes('bank')) {
    reasons.push('category aligned with banking intent')
  }

  return reasons.join(', ')
}

function deriveCategory(preview: string, query: string) {
  const text = `${preview} ${query}`.toLowerCase()
  if (text.includes('nifty') || text.includes('index')) return 'Indices'
  if (text.includes('bank')) return 'Banking'
  if (text.includes('fed') || text.includes('macro')) return 'Macro'
  return 'General'
}

export default function DiscoverInsightsPage() {
  const navigate = useNavigate()
  const { setSelectedInsight, setSellerMetadata } = useAppContext()

  const [query, setQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('All')
  const [priceFilter, setPriceFilter] = useState('Any')
  const [reputationFilter, setReputationFilter] = useState('Any')
  const [recencyFilter, setRecencyFilter] = useState('Any')
  const [phase, setPhase] = useState<SearchPhase>('idle')
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('unknown')
  const [hasSearched, setHasSearched] = useState(false)
  const [rawInsights, setRawInsights] = useState<RankedInsight[]>([])
  const [weakOnly, setWeakOnly] = useState(false)
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null)

  const recencyInHours = (recency: string) => {
    if (recency.includes('h')) return Number.parseInt(recency, 10)
    if (recency.includes('d')) return Number.parseInt(recency, 10) * 24
    if (recency === 'Live') return 1
    return Number.POSITIVE_INFINITY
  }

  const applyFilters = (insight: RankedInsight) => {
    const matchesCategory = categoryFilter === 'All' || insight.category === categoryFilter
    const matchesPrice =
      priceFilter === 'Any' ||
      (priceFilter === 'Under 2' && insight.price < 2) ||
      (priceFilter === '2 to 3' && insight.price >= 2 && insight.price <= 3) ||
      (priceFilter === 'Above 3' && insight.price > 3)
    const matchesReputation =
      reputationFilter === 'Any' ||
      (reputationFilter === '70+' && insight.reputation >= 70) ||
      (reputationFilter === '85+' && insight.reputation >= 85)

    const ageHours = recencyInHours(insight.recency)
    const matchesRecency =
      recencyFilter === 'Any' ||
      (recencyFilter === 'Under 6h' && ageHours <= 6) ||
      (recencyFilter === 'Under 24h' && ageHours <= 24)

    return matchesCategory && matchesPrice && matchesReputation && matchesRecency
  }

  const visibleInsights = (hasSearched ? rawInsights : DEMO_INSIGHTS).filter(applyFilters)

  const runSearch = async () => {
    setHasSearched(true)
    setPhase('fetching')
    setWeakOnly(false)
    setSearchFeedback(null)
    setRawInsights([])

    const searchQuery = query.trim()
    if (!searchQuery) {
      setPhase('ready')
      setSearchFeedback('Please enter a market question to rank live insights.')
      return
    }

    try {
      const response = await api.discoverInsights(searchQuery)
      setBackendStatus('online')

      setPhase('evaluating')
      await new Promise((resolve) => setTimeout(resolve, 450))

      const mapped: RankedInsight[] = response.matches.map((match, index) => {
        const relevance = Math.max(1, Math.min(99, Math.round(match.score * 100)))
        const wallet = match.seller_wallet || 'Seller wallet unavailable'
        const category = deriveCategory(match.insight_preview, searchQuery)
        const riskSignal = match.reputation < 70 ? 'Below trust threshold' : 'Low risk'

        return {
          id: `${match.listing_id}-${index}`,
          title: match.insight_preview,
          seller: wallet.slice(0, 8) + '...'.repeat(wallet.length > 12 ? 1 : 0),
          wallet,
          price: match.price_usdc,
          reputation: Number(match.reputation || 0),
          relevance,
          reason: summarizeReason(match, relevance, searchQuery),
          category,
          recency: 'Live',
          listingStatus: match.listing_status || 'Active',
          riskSignal,
          txId: 'Pending reveal',
          cid: match.cid,
          listingId: `L-${match.listing_id}`,
          asaId: String(match.asa_id),
        }
      })

      const strongCandidates = mapped.filter(
        (insight) => insight.reputation >= 75 && insight.relevance >= 72 && insight.price <= 3,
      )

      setRawInsights(mapped)
      if (response.degraded) {
        setSearchFeedback(
          response.message ||
            `Search degraded (${response.diagnostics?.code || 'unknown'}). Please retry shortly.`,
        )
      } else if (mapped.length === 0) {
        setSearchFeedback(
          response.message || 'No suitable insight found for this query and filter combination.',
        )
      } else if (strongCandidates.length === 0) {
        setWeakOnly(true)
        setSearchFeedback('Results found, but trust/value strength is weak. Review risk signals carefully.')
      } else {
        setSearchFeedback('Ranked results are ready. Mercator scored relevance, reputation, and value.')
      }

      setPhase('ready')
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.userMessage
          : 'Mercator backend is currently unreachable. Please retry in a moment.'
      setBackendStatus('offline')
      setRawInsights([])
      setWeakOnly(false)
      setSearchFeedback(message)
      setPhase('ready')
    }
  }

  const handleSelectInsight = (insight: RankedInsight) => {
    setSelectedInsight({
      insight_text: insight.title,
      price: insight.price,
      seller_wallet: insight.wallet,
      seller_reputation: insight.reputation,
      relevance_score: insight.relevance,
      query_text: query.trim(),
      market_context: insight.category,
      synopsis: insight.reason,
      listing_id: insight.listingId,
      cid: insight.cid,
      tx_id: insight.txId,
      asa_id: insight.asaId,
    })

    setSellerMetadata({
      reputation: insight.reputation,
      address: insight.wallet,
      totalSales: insight.reputation > 80 ? 18 : 9,
      listingStatus: insight.listingStatus,
      riskSignal: insight.riskSignal,
      rankingReason: insight.reason,
    })

    navigate('/evaluate')
  }

  return (
    <div className="discover-page">
      <section className="discover-hero">
        <div className="home-wrap discover-layout">
          <div className="discover-hero-copy">
            <p className="home-kicker">Buyer Console</p>
            <h1>Ask Mercator a market question and get ranked answers.</h1>
            <p>
              Enter a natural-language query and Mercator will search, rank, and justify insights
              using relevance, reputation, and value.
            </p>

            <div className="discover-search-console">
              <label className="discover-input-group">
                <span>Market question</span>
                <input
                  type="text"
                  placeholder="NIFTY breakout setup today"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
                <small>
                  Try prompts like "best short-term bank index insight" or "NIFTY breakout setup
                  today".
                </small>
              </label>

              <button type="button" className="discover-submit-btn" onClick={runSearch}>
                {phase === 'fetching' || phase === 'evaluating' ? 'Running Search...' : 'Search Insights'}
              </button>
            </div>

            <div className="discover-search-status">
              <p>
                Backend scoring dimensions: relevance, reputation, and value.
                {backendStatus === 'online' && ' Backend online.'}
                {backendStatus === 'offline' && ' Backend offline.'}
                {backendStatus === 'unknown' && ' Backend status will be verified on search.'}
              </p>
              {searchFeedback && <p>{searchFeedback}</p>}
            </div>
          </div>

          <aside className="discover-sidecard">
            <p className="home-kicker">What happens next</p>
            <ul>
              <li>Mercator searches live listings from the backend.</li>
              <li>Results are ranked by topical fit, reputation, and value.</li>
              <li>Choose one result to continue into evaluation and approval.</li>
            </ul>
          </aside>
        </div>
      </section>

      <section className="discover-results">
        <div className="home-wrap discover-results-shell">
          <div className="discover-results-head">
            <div>
              <p className="home-kicker">Ranked Results</p>
              <h2>{query ? `Matches for "${query}"` : 'Ranked insights ready to compare'}</h2>
            </div>

            <div className="discover-filters">
              <label>
                <span>Category</span>
                <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                  <option>All</option>
                  <option>Indices</option>
                  <option>Banking</option>
                  <option>Macro</option>
                  <option>General</option>
                </select>
              </label>
              <label>
                <span>Price</span>
                <select value={priceFilter} onChange={(event) => setPriceFilter(event.target.value)}>
                  <option>Any</option>
                  <option>Under 2</option>
                  <option>2 to 3</option>
                  <option>Above 3</option>
                </select>
              </label>
              <label>
                <span>Reputation</span>
                <select value={reputationFilter} onChange={(event) => setReputationFilter(event.target.value)}>
                  <option>Any</option>
                  <option>70+</option>
                  <option>85+</option>
                </select>
              </label>
              <label>
                <span>Recency</span>
                <select value={recencyFilter} onChange={(event) => setRecencyFilter(event.target.value)}>
                  <option>Any</option>
                  <option>Under 6h</option>
                  <option>Under 24h</option>
                </select>
              </label>
            </div>
          </div>

          {phase === 'fetching' && (
            <div className="discover-phase-card">
              <p className="home-kicker">Searching listings</p>
              <h3>Fetching candidate insights from the network...</h3>
              <p>Mercator is retrieving listings and preparing semantic comparison.</p>
            </div>
          )}

          {phase === 'evaluating' && (
            <div className="discover-phase-card discover-phase-card--reasoning">
              <p className="home-kicker">Agent evaluation</p>
              <h3>Scoring trust, relevance, and value for your query...</h3>
              <p>
                The agent is reasoning over query fit, seller reputation thresholds, and price
                fairness before presenting ranked outcomes.
              </p>
            </div>
          )}

          {phase === 'ready' && hasSearched && visibleInsights.length === 0 && (
            <div className="discover-empty-state">
              <h3>No suitable insight found for this query.</h3>
              <p>
                Try a more specific market context, reduce filters, or broaden the time horizon in
                your prompt.
              </p>
              <ul>
                <li>Use instrument + timeframe (example: "NIFTY breakout setup for today").</li>
                <li>Relax reputation or category filters.</li>
                <li>Try a broader intent (example: "short-term banking insight").</li>
              </ul>
            </div>
          )}

          {phase === 'ready' && hasSearched && visibleInsights.length > 0 && weakOnly && (
            <div className="discover-empty-state discover-empty-state--weak">
              <h3>No strong candidate passed trust/value thresholds.</h3>
              <p>
                Results exist, but they are currently weaker in reputation, topical fit, or value.
                Review risk signals before continuing.
              </p>
            </div>
          )}

          <div className="discover-results-grid">
            {visibleInsights.map((insight, index) => (
              <article key={insight.id} className="discover-result-card">
                <div className="discover-result-topline">
                  <span className="discover-rank">#{index + 1}</span>
                  <span className="discover-category">{insight.category}</span>
                  <span className="discover-recency">{insight.recency}</span>
                </div>

                <h3>{insight.title}</h3>
                <p className="discover-seller">
                  by {insight.seller} · {insight.wallet}
                </p>
                <p className="discover-reason">{insight.reason}</p>

                <div className="discover-metrics">
                  <div>
                    <span>Relevance</span>
                    <strong>{insight.relevance}%</strong>
                  </div>
                  <div>
                    <span>Reputation</span>
                    <strong>{insight.reputation}</strong>
                  </div>
                  <div>
                    <span>Price</span>
                    <strong>{insight.price} USDC</strong>
                  </div>
                </div>

                <div className="discover-trust-cues">
                  <span className="discover-status-chip">Listing {insight.listingStatus}</span>
                  <span className={`discover-risk-chip ${insight.reputation < 75 ? 'is-risk' : ''}`}>
                    {insight.reputation < 75 ? 'Below trust threshold' : insight.riskSignal}
                  </span>
                </div>

                <div className="discover-logic">
                  <p>
                    <strong>Why ranked here:</strong> {insight.reason}.
                  </p>
                </div>

                <button onClick={() => handleSelectInsight(insight)} className="discover-evaluate-btn">
                  Choose This Insight
                </button>
              </article>
            ))}
          </div>

          <div className="discover-footer-note">
            <p>
              Mercator is ranking the insights, not just listing them.{' '}
              <a href="/trust">Learn how reputation and skip logic affect ranking.</a>
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

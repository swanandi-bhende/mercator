import { useEffect, useMemo, useState, useRef } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { api, ApiError } from '../utils/api'
import type { DiscoverMatch, ListingsFeedItem } from '../types'
import VerifiedBadge from '../components/shared/VerifiedBadge'
import { SellerCard } from '../components/SellerCard'
import ExpiryCountdown from '../components/ExpiryCountdown'
import '../styles/listing.css'
import type { LayoutOutletContext } from '../components/Layout'

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
  state?: string
  expiry_round?: number
  sourceType?: string
}

type LiveListing = {
  listing_id: string
  seller_wallet: string
  seller_name: string
  price_usdc: number
  insight_preview: string
  source_type: string
  ipfs_cid: string
  listing_tx_id: string
  reputation_score: number
  state?: string
  expiry_round?: number
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

function tokenize(value: string) {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/g)
    .map((token) => token.trim())
    .filter((token) => token.length > 1)
}

function buildFeaturedListingInsight(listingInsight: ReturnType<typeof useAppContext>['listingInsight']) {
  if (!listingInsight) return null

  return {
    id: listingInsight.tx_id || listingInsight.listing_id || listingInsight.cid || 'recent-listing',
    title: listingInsight.insight_text,
    seller: listingInsight.seller_wallet.slice(0, 8) + '...',
    wallet: listingInsight.seller_wallet,
    price: listingInsight.price,
    reputation: Number(listingInsight.seller_reputation ?? 87),
    relevance: Number(listingInsight.relevance_score ?? 99),
    reason: 'Recently published listing from your last seller flow.',
    category: deriveCategory(listingInsight.insight_text, listingInsight.market_context || ''),
    recency: 'Live',
    listingStatus: 'Recent',
    riskSignal: 'Fresh listing',
    txId: listingInsight.tx_id || 'Pending reveal',
    cid: listingInsight.cid || '',
    listingId: listingInsight.listing_id || '',
    asaId: listingInsight.asa_id || '',
    sourceType: 'listing',
  } satisfies RankedInsight
}

function toLiveListing(item: ListingsFeedItem): LiveListing {
  return {
    listing_id: String(item.listing_id),
    seller_wallet: item.seller_wallet,
    seller_name: item.seller_wallet.slice(0, 8),
    price_usdc: Number(item.price_usdc || 0),
    insight_preview: item.insight_text,
    source_type: item.source_type || 'listing',
    ipfs_cid: item.cid,
    listing_tx_id: item.tx_id,
    reputation_score: Number(item.seller_reputation || 0),
    state: (item.state || 'active'),
    expiry_round: Number(item.expiry_round || 0),
  }
}

function mapLiveListingToRankedInsight(item: LiveListing): RankedInsight {
  return {
    id: `live-${item.listing_id}`,
    title: item.insight_preview,
    seller: item.seller_name,
    wallet: item.seller_wallet,
    price: Number(item.price_usdc || 0),
    reputation: Number(item.reputation_score || 0),
    relevance: 99,
    reason: `Live ${item.source_type} listing received over WebSocket.`,
    category: deriveCategory(item.insight_preview, ''),
    recency: 'Live',
    listingStatus: 'Live',
    riskSignal: item.reputation_score < 75 ? 'Below trust threshold' : 'Low risk',
    txId: item.listing_tx_id,
    cid: item.ipfs_cid,
    listingId: String(item.listing_id),
    asaId: '0',
    sourceType: item.source_type || 'listing',
  }
}

export default function DiscoverInsightsPage() {
  const navigate = useNavigate()
  const { latestWsEvent } = useOutletContext<LayoutOutletContext>()
  const { listingInsight, setSelectedInsight, setSellerMetadata, buyerWallet, setBuyerWallet } = useAppContext()

  const [query, setQuery] = useState(() => {
    if (typeof window === 'undefined') return ''
    return sessionStorage.getItem('discover:lastQuery') || ''
  })
  const [categoryFilter, setCategoryFilter] = useState('All')
  const [priceFilter, setPriceFilter] = useState('Any')
  const [reputationFilter, setReputationFilter] = useState('Any')
  const [sourceTypeFilter, setSourceTypeFilter] = useState('Any')
  const [recencyFilter, setRecencyFilter] = useState('Any')
  const [phase, setPhase] = useState<SearchPhase>(() => {
    if (typeof window === 'undefined') return 'idle'
    const hasResults = sessionStorage.getItem('discover:lastResults')
    return hasResults ? 'ready' : 'idle'
  })
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('unknown')
  const [hasSearched, setHasSearched] = useState(() => {
    if (typeof window === 'undefined') return false
    return Boolean(sessionStorage.getItem('discover:lastResults'))
  })
  const [rawInsights, setRawInsights] = useState<RankedInsight[]>(() => {
    if (typeof window === 'undefined') return []
    const raw = sessionStorage.getItem('discover:lastResults')
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })
  const [weakOnly, setWeakOnly] = useState(false)
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null)
  const [subscriptionStatus, setSubscriptionStatus] = useState<{
    active: boolean
    expiry_round: number
    expiry_approx_date: string
    months_remaining: number
    total_months_paid: number
    total_usdc_paid_micro: number
  } | null>(null)
  const [subscriptionMonths, setSubscriptionMonths] = useState(1)
  const [subscriptionLoading, setSubscriptionLoading] = useState(false)
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null)
  const [listings, setListings] = useState<LiveListing[]>([])
  const [currentRound, setCurrentRound] = useState<number>(0)
  const [newListingIds, setNewListingIds] = useState<string[]>([])
  const [agentBadges, setAgentBadges] = useState<Record<string, string>>({})
  const [reputationOverrides, setReputationOverrides] = useState<Record<string, number>>({})
  const [topSellers, setTopSellers] = useState<any[]>([])
  const [topSellersLoading, setTopSellersLoading] = useState(false)

  const reputationCacheRef = useRef<
    Map<string, { score: number; fetchedAt: number }>
  >(new Map())

  const queryTokens = useMemo(() => tokenize(query), [query])
  const featuredListing = useMemo(() => buildFeaturedListingInsight(listingInsight), [listingInsight])
  const liveInsights = useMemo(() => listings.map(mapLiveListingToRankedInsight), [listings])
  const makeIpfsUrl = (cid: string) => (cid ? `https://gateway.pinata.cloud/ipfs/${cid}` : '')
  const sourceTypeOptions = useMemo(() => {
    const options = new Set<string>(['Any'])
    ;[...rawInsights, ...liveInsights, ...(featuredListing ? [featuredListing] : [])].forEach((insight) => {
      options.add((insight as RankedInsight).sourceType || 'semantic')
    })
    return Array.from(options)
  }, [rawInsights, liveInsights, featuredListing])

  const recencyInHours = (recency: string) => {
    if (recency.includes('h')) return Number.parseInt(recency, 10)
    if (recency.includes('d')) return Number.parseInt(recency, 10) * 24
    if (recency === 'Live') return 1
    return Number.POSITIVE_INFINITY
  }

  const getQueryMatchScore = (insight: RankedInsight) => {
    if (queryTokens.length === 0) return 1
    const haystackTokens = tokenize(
      [insight.title, insight.seller, insight.wallet, insight.category, insight.reason].join(' '),
    )
    const overlap = queryTokens.filter((token) => haystackTokens.includes(token)).length
    return overlap / queryTokens.length
  }

  const matchesSearchQuery = (insight: RankedInsight) => {
    if (queryTokens.length === 0) return true
    const score = getQueryMatchScore(insight)
    if (score > 0) return true

    const lowerQuery = query.trim().toLowerCase()
    const lowerText = [insight.title, insight.reason, insight.category, insight.wallet]
      .join(' ')
      .toLowerCase()
    return lowerText.includes(lowerQuery) || lowerQuery.includes(lowerText)
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
    const matchesSourceType =
      sourceTypeFilter === 'Any' || (insight.sourceType || 'semantic') === sourceTypeFilter

    const ageHours = recencyInHours(insight.recency)
    const matchesRecency =
      recencyFilter === 'Any' ||
      (recencyFilter === 'Under 6h' && ageHours <= 6) ||
      (recencyFilter === 'Under 24h' && ageHours <= 24)

    return matchesCategory && matchesPrice && matchesReputation && matchesSourceType && matchesRecency
  }

  const baseInsights = hasSearched
    ? rawInsights
    : liveInsights.length > 0
      ? liveInsights
      : featuredListing
        ? [featuredListing, ...DEMO_INSIGHTS]
        : DEMO_INSIGHTS
  const visibleInsights = baseInsights.filter((insight) => applyFilters(insight) && matchesSearchQuery(insight))

  // Apply reputation overrides from cache/WebSocket updates
  const insightsWithLiveReputation = useMemo(
    () =>
      visibleInsights.map((insight) => ({
        ...insight,
        reputation: reputationOverrides[insight.wallet] ?? insight.reputation,
      })),
    [visibleInsights, reputationOverrides],
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    sessionStorage.setItem('discover:lastQuery', query)
  }, [query])

  useEffect(() => {
    let cancelled = false

    const refreshSubscriptionStatus = async () => {
      if (!buyerWallet) {
        setSubscriptionStatus(null)
        setSubscriptionError(null)
        return
      }

      try {
        const status = await api.subscriptionStatus(buyerWallet)
        if (cancelled) return
        setSubscriptionStatus({
          active: Boolean(status.active),
          expiry_round: Number(status.expiry_round || 0),
          expiry_approx_date: String(status.expiry_approx_date || ''),
          months_remaining: Number(status.months_remaining || 0),
          total_months_paid: Number(status.total_months_paid || 0),
          total_usdc_paid_micro: Number(status.total_usdc_paid_micro || 0),
        })
        setSubscriptionError(null)
      } catch (error) {
        if (cancelled) return
        setSubscriptionStatus(null)
        setSubscriptionError(error instanceof Error ? error.message : 'Unable to load subscription status')
      }
    }

    void refreshSubscriptionStatus()

    return () => {
      cancelled = true
    }
  }, [buyerWallet])

  useEffect(() => {
    let cancelled = false

    const loadListings = async () => {
      try {
        const response = await api.listingsFeed(50)
        if (cancelled || !response.success) return
        const mapped = (response.listings || []).map(toLiveListing)
        setListings(mapped)
      } catch {
        // Best-effort preload only.
      }
    }

    void loadListings()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const loadTopSellers = async () => {
      try {
        setTopSellersLoading(true)
        const sellers = await api.sellerLeaderboard(5)
        if (cancelled) return
        setTopSellers(sellers || [])
      } catch {
        // Best-effort load - if leaderboard fails, just don't show it
        setTopSellers([])
      } finally {
        if (!cancelled) setTopSellersLoading(false)
      }
    }

    void loadTopSellers()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const fetchSellerReputation = async (wallet: string) => {
      if (!wallet || cancelled) return

      const cached = reputationCacheRef.current.get(wallet)
      if (cached && Date.now() - cached.fetchedAt < 60000) {
        setReputationOverrides((prev) => ({
          ...prev,
          [wallet]: cached.score,
        }))
        return
      }

      try {
        const data = await api.get<{ effective_score: number }>(
          `/sellers/${wallet}/reputation`,
        )
        if (cancelled) return
        if (data && typeof data.effective_score === 'number') {
          reputationCacheRef.current.set(wallet, {
            score: data.effective_score,
            fetchedAt: Date.now(),
          })
          setReputationOverrides((prev) => ({
            ...prev,
            [wallet]: data.effective_score,
          }))
        }
      } catch {
        // Best-effort; use existing reputation from listing
      }
    }

    const uniqueSellers = new Set(visibleInsights.map((i) => i.wallet))
    Promise.all(
      Array.from(uniqueSellers).map((wallet) => fetchSellerReputation(wallet)),
    ).catch(() => {
      // Ignore errors; reputation is optional
    })

    return () => {
      cancelled = true
    }
  }, [visibleInsights])

  useEffect(() => {
    if (!latestWsEvent) return

    if (latestWsEvent.event_type === 'new_listing') {
      const payload = latestWsEvent.payload
      const listing: LiveListing = {
        listing_id: String(payload.listing_id || ''),
        seller_wallet: String(payload.seller_wallet || ''),
        seller_name: String(payload.seller_name || 'seller'),
        price_usdc: Number(payload.price_usdc || 0),
        insight_preview: String(payload.insight_preview || ''),
        source_type: String(payload.source_type || 'listing'),
        ipfs_cid: String(payload.ipfs_cid || ''),
        listing_tx_id: String(payload.listing_tx_id || ''),
        reputation_score: Number(payload.reputation_score || 0),
      }

      if (!listing.listing_id) return

      setListings((prev) => {
        const deduped = prev.filter((item) => item.listing_id !== listing.listing_id)
        return [listing, ...deduped.slice(0, 49)]
      })

      setNewListingIds((prev) => (prev.includes(listing.listing_id) ? prev : [...prev, listing.listing_id]))
      window.setTimeout(() => {
        setNewListingIds((prev) => prev.filter((id) => id !== listing.listing_id))
      }, 2000)
    }

    if (latestWsEvent.event_type === 'listing.expired') {
      const payload = latestWsEvent.payload
      const listingId = String(payload.listing_id || '')
      if (listingId) {
        setListings((prev) => prev.map((it) => (it.listing_id === listingId ? { ...it, state: 'expired' } : it)))
        setRawInsights((prev) => prev.map((it) => (it.listingId === `L-${listingId}` ? { ...it, listingStatus: 'expired', state: 'expired' } : it)))
      }
    }

    if (latestWsEvent.event_type === 'health_update') {
      const payload = latestWsEvent.payload as Record<string, unknown>
      const round = Number(payload.current_round || payload.last_round || 0)
      if (round && round > 0) setCurrentRound(round)
    }

    if (latestWsEvent.event_type === 'autonomous_decision') {
      const payload = latestWsEvent.payload
      const listingId = String(payload.listing_id || '')
      if (!listingId) return

      const decision = String(payload.decision || 'SKIP').toUpperCase()
      const rejectionReason = String(payload.rejection_reason || '').trim()
      const label = decision === 'BUY' ? '🤖 Agent BUY' : `🤖 Agent SKIP${rejectionReason ? `: ${rejectionReason}` : ''}`

      setAgentBadges((prev) => ({ ...prev, [listingId]: label }))
      window.setTimeout(() => {
        setAgentBadges((prev) => {
          const next = { ...prev }
          delete next[listingId]
          return next
        })
      }, 5000)
    }

    if (latestWsEvent.event_type === 'reputation_updated') {
      const payload = latestWsEvent.payload as Record<string, unknown>
      const sellerWallet = String(payload.wallet || '')
      if (!sellerWallet) return

      const effectiveScore = Number(payload.effective_score || 0)
      reputationCacheRef.current.delete(sellerWallet)
      setReputationOverrides((prev) => ({
        ...prev,
        [sellerWallet]: effectiveScore,
      }))
    }
  }, [latestWsEvent])

  const handleSubscribe = async () => {
    if (!buyerWallet) {
      setSubscriptionError('Enter a buyer wallet before subscribing.')
      return
    }

    setSubscriptionLoading(true)
    setSubscriptionError(null)
    try {
      const response = await api.subscribe(buyerWallet, subscriptionMonths)
      setSubscriptionStatus({
        active: true,
        expiry_round: Number(response.expiry_round || 0),
        expiry_approx_date: String(response.expiry_approx_date || ''),
        months_remaining: Number(subscriptionMonths),
        total_months_paid: Number(response.months_paid || subscriptionMonths),
        total_usdc_paid_micro: Number(subscriptionMonths) * 50000000,
      })
      setSubscriptionMonths(1)
    } catch (error) {
      setSubscriptionError(error instanceof Error ? error.message : 'Subscription failed')
    } finally {
      setSubscriptionLoading(false)
    }
  }

  const renewSubscription = () => {
    setSubscriptionMonths(1)
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (hasSearched) {
      sessionStorage.setItem('discover:lastResults', JSON.stringify(rawInsights))
    }
  }, [hasSearched, rawInsights])

  const runSearch = async () => {
    setHasSearched(true)
    setPhase('fetching')
    setWeakOnly(false)
    setSearchFeedback(null)
    setRawInsights([])

    const searchQuery = query.trim()
    if (!searchQuery) {
      setPhase('ready')
      setSearchFeedback(
        featuredListing
          ? 'Showing your most recent listing. Enter a market question to rank live insights.'
          : 'Please enter a market question to rank live insights.',
      )
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
          state: String(match.state || match.listing_state || 'active'),
          expiry_round: Number(match.expiry_round || match.expiry || 0),
          sourceType: String(match.source_type || 'semantic'),
        }
      })

      const queryFiltered = mapped.filter((insight) => matchesSearchQuery(insight))
      const featuredMatchesQuery = featuredListing && matchesSearchQuery(featuredListing) ? featuredListing : null
      const mergedMatches = featuredMatchesQuery
        ? [
            featuredMatchesQuery,
            ...queryFiltered.filter(
              (insight) =>
                insight.id !== featuredMatchesQuery.id && insight.listingId !== featuredMatchesQuery.listingId,
            ),
          ]
        : queryFiltered

      const strongCandidates = mergedMatches.filter(
        (insight) => insight.reputation >= 75 && insight.relevance >= 72 && insight.price <= 3,
      )

      setRawInsights(mergedMatches)
      sessionStorage.setItem('discover:lastResults', JSON.stringify(mergedMatches))
      sessionStorage.setItem('discover:lastQuery', searchQuery)
      if (response.degraded) {
        setSearchFeedback(
          response.message ||
            `Search degraded (${response.diagnostics?.code || 'unknown'}). Please retry shortly.`,
        )
      } else if (mergedMatches.length === 0) {
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

            <div className={`discover-subscription-panel ${subscriptionStatus?.active ? 'is-active' : ''}`}>
              <div className="discover-subscription-panel__heading">
                <div>
                  <p className="home-kicker">Subscription</p>
                  <h2>{subscriptionStatus?.active ? 'Subscribed' : 'Unlimited Curator Insights'}</h2>
                  <p>
                    {subscriptionStatus?.active
                      ? `Expires approximately ${subscriptionStatus.expiry_approx_date} (round ${subscriptionStatus.expiry_round})`
                      : '50 USDC / month — all Curator Agent listings included, no per-insight fees'}
                  </p>
                </div>
                {subscriptionStatus?.active && <span className="discover-subscription-badge">✓ Active</span>}
              </div>

              <label className="discover-input-group">
                <span>Buyer wallet</span>
                <input
                  type="text"
                  placeholder="Enter your Algorand wallet"
                  value={buyerWallet ?? ''}
                  onChange={(event) => setBuyerWallet(event.target.value)}
                />
              </label>

              <div className="discover-subscription-panel__controls">
                <label className="discover-input-group">
                  <span>Months</span>
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={subscriptionMonths}
                    onChange={(event) => setSubscriptionMonths(Number(event.target.value) || 1)}
                  />
                </label>

                <button
                  type="button"
                  className="discover-submit-btn discover-subscription-btn"
                  onClick={handleSubscribe}
                  disabled={subscriptionLoading}
                >
                  {subscriptionLoading ? 'Processing...' : subscriptionStatus?.active ? 'Renew' : 'Subscribe Now'}
                </button>
              </div>

              {subscriptionStatus?.active && (
                <p className="discover-subscription-meta">
                  {subscriptionStatus.total_months_paid} month(s) paid · {subscriptionStatus.total_usdc_paid_micro / 1_000_000} USDC total · {subscriptionStatus.months_remaining.toFixed(2)} months remaining
                </p>
              )}

              {subscriptionError && <p className="discover-subscription-error">{subscriptionError}</p>}

              {subscriptionStatus?.active && (
                <button type="button" className="discover-side-link" onClick={renewSubscription}>
                  Renew
                </button>
              )}

              <button type="button" className="discover-side-link" onClick={() => navigate('/subscription')}>
                Open Subscription Manager
              </button>
            </div>

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
            <button className="discover-side-link" onClick={() => navigate('/activity')}>
              Open Activity Ledger
            </button>
            <button className="discover-side-link" onClick={() => navigate('/trust')}>
              Understand Reputation Rules
            </button>

            {/* Top Sellers Panel */}
            <div className="discover-top-sellers-panel">
              <p className="home-kicker">Top Sellers</p>
              {topSellersLoading ? (
                <p style={{ color: '#999', fontSize: '14px' }}>Loading top sellers...</p>
              ) : topSellers.length > 0 ? (
                <div className="discover-top-sellers-list">
                  {topSellers.map((seller, index) => (
                    <div key={seller.seller_wallet} className="discover-top-seller-item">
                      <span className="discover-top-seller-rank">#{index + 1}</span>
                      <SellerCard wallet={seller.seller_wallet} />
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#999', fontSize: '14px' }}>No sellers yet</p>
              )}
            </div>
          </aside>
        </div>
      </section>

      <section className="discover-results">
        <div className="home-wrap discover-results-shell">
          <div className="discover-results-head">
            <div>
              <p className="home-kicker">Ranked Results</p>
              <h2>{query ? `Matches for "${query}"` : featuredListing ? 'Your latest listing is ready to compare' : 'Ranked insights ready to compare'}</h2>
              <button className="discover-results-link" onClick={() => navigate('/trust')}>
                Open Trust / Reputation Guide
              </button>
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
                <span>Source Type</span>
                <select value={sourceTypeFilter} onChange={(event) => setSourceTypeFilter(event.target.value)}>
                  {sourceTypeOptions.map((sourceType) => (
                    <option key={sourceType} value={sourceType}>
                      {sourceType === 'Any' ? 'Any' : sourceType}
                    </option>
                  ))}
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
                Try a more specific market context, reduce filters, or clear the search if you want
                to review the latest listing.
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
            {insightsWithLiveReputation.map((insight, index) => (
              <article
                key={insight.id}
                className={`discover-result-card ${newListingIds.includes(insight.listingId) ? 'listing-card-new' : ''} ${(insight.state || insight.listingStatus || '').toLowerCase() === 'expired' ? 'listing-expired' : ''} ${(insight.state || insight.listingStatus || '').toLowerCase() === 'sold' ? 'listing-sold' : ''}`}
              >
                {agentBadges[insight.listingId] && (
                  <div className="discover-agent-badge" role="status" aria-live="polite">
                    {agentBadges[insight.listingId]}
                  </div>
                )}
                <div className="discover-result-topline">
                  <span className="discover-rank">#{index + 1}</span>
                  <span className="discover-category">{insight.category}</span>
                  <span className="discover-recency">{insight.recency}</span>
                </div>

                <h3>{insight.title}</h3>
                <SellerCard wallet={insight.wallet} />
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
                  <span className="discover-status-chip">Listing {insight.listingStatus || (insight.state || 'active')}</span>
                  <span className={`discover-risk-chip ${insight.reputation < 75 ? 'is-risk' : ''}`}>
                    {insight.reputation < 75 ? 'Below trust threshold' : insight.riskSignal}
                  </span>
                  <VerifiedBadge walletAddress={insight.wallet} compact={true} />
                </div>

                <div className="discover-preview-strip">
                  <div>
                    <span>CID</span>
                    <strong>{insight.cid ? `${insight.cid.slice(0, 12)}...` : 'Unavailable'}</strong>
                  </div>
                  <div>
                    <span>TX</span>
                    <strong>{insight.txId && insight.txId !== 'Pending reveal' ? `${insight.txId.slice(0, 10)}...` : 'Pending'}</strong>
                  </div>
                  <div>
                    <span>Status</span>
                    <strong>{(insight.state || insight.listingStatus || 'active').toLowerCase()}</strong>
                  </div>
                </div>

                <div className="discover-logic">
                  <p>
                    <strong>Why ranked here:</strong> {insight.reason}.
                  </p>
                </div>

                <div className="discover-card-actions">
                  <ExpiryCountdown
                    expiry_round={Number(insight.expiry_round || 0)}
                    current_round={currentRound}
                    state={(insight.state || insight.listingStatus || '').toLowerCase()}
                    onExpired={() => {
                      // visually update this insight to expired
                      setRawInsights((prev) => prev.map((it) => (it.id === insight.id ? { ...it, listingStatus: 'expired', state: 'expired' } : it)))
                    }}
                  />
                  <div className="discover-card-action-row">
                    {insight.cid ? (
                      <a className="discover-preview-link" href={makeIpfsUrl(insight.cid)} target="_blank" rel="noreferrer">
                        Open IPFS
                      </a>
                    ) : (
                      <span className="discover-preview-link is-disabled">No IPFS preview</span>
                    )}
                    <button onClick={() => handleSelectInsight(insight)} className="discover-evaluate-btn">
                      Choose This Insight
                    </button>
                  </div>
                </div>
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

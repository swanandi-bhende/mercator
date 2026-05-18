import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../utils/api'
import type {
  SellerProfileResponse,
  ListingHistoryEntry,
  ReputationHistoryEntry,
  SellerPurchaseHistoryEntry,
  SellerReputationResponse,
} from '../types'
import './SellerProfile.css'
import '../styles/listing.css'

/**
 * Get reputation badge color
 */
function getReputationBadgeClass(score: number): string {
  if (score >= 80) return 'reputation-badge reputation-badge--excellent'
  if (score >= 70) return 'reputation-badge reputation-badge--good'
  if (score >= 50) return 'reputation-badge reputation-badge--fair'
  return 'reputation-badge reputation-badge--poor'
}

/**
 * Truncate wallet address
 */
function truncateWallet(wallet: string): string {
  return `${wallet.slice(0, 8)}...${wallet.slice(-4)}`
}

/**
 * Format USDC balance from microunits
 */
function formatUsdc(micro: number): string {
  return (micro / 1000000).toLocaleString('en-US', { maximumFractionDigits: 2 })
}

/**
 * Deterministic avatar color from wallet hash
 */
function getAvatarColor(wallet: string): string {
  const hex = wallet.slice(0, 6)
  const hue = parseInt(hex, 16) % 360
  return `hsl(${hue}, 70%, 60%)`
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    alert(`Copied: ${text}`)
  })
}

interface SellerProfilePageProps {}

export const SellerProfilePage: React.FC<SellerProfilePageProps> = () => {
  const { wallet } = useParams<{ wallet: string }>()
  const navigate = useNavigate()

  const [profile, setProfile] = useState<SellerProfileResponse | null>(null)
  const [listings, setListings] = useState<ListingHistoryEntry[]>([])
  const [reputationHistory, setReputationHistory] = useState<ReputationHistoryEntry[]>([])
  const [purchaseHistory, setPurchaseHistory] = useState<SellerPurchaseHistoryEntry[]>([])
  const [reputationSummary, setReputationSummary] = useState<SellerReputationResponse | null>(null)
  const [purchaseNote, setPurchaseNote] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(10)
  const [totalPages, setTotalPages] = useState(0)

  const fetchData = useCallback(async () => {
    if (!wallet) return

    try {
      setLoading(true)
      setError(null)

      // Fetch profile (Tier 1 & 2 data)
      const profileData = await api.sellerProfile(wallet)
      setProfile(profileData)

      try {
        const reputationData = await api.sellerReputation(wallet)
        setReputationSummary(reputationData)
      } catch {
        setReputationSummary(null)
      }

      // Fetch reputation history for sparkline
      try {
        const reputationData = await api.sellerReputationHistory(wallet)
        setReputationHistory(reputationData.history || [])
      } catch {
        setReputationHistory(profileData.reputation_history || [])
      }

      try {
        const purchaseData = await api.sellerPurchaseHistory(wallet, 20)
        setPurchaseHistory(purchaseData.purchase_history || [])
        setPurchaseNote(purchaseData.note || null)
      } catch {
        setPurchaseHistory([])
        setPurchaseNote(null)
      }

      // Fetch listings for current page
      const listingsData = await api.sellerListings(wallet, currentPage, pageSize)
      setListings(listingsData.listings || [])
      setTotalPages(listingsData.total_pages || 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load seller profile')
      console.error('Error fetching seller profile:', err)
    } finally {
      setLoading(false)
    }
  }, [wallet, currentPage, pageSize])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  if (!wallet) {
    return (
      <div className="seller-profile-page">
        <div className="error-message">Invalid seller wallet address</div>
      </div>
    )
  }

  if (loading && !profile) {
    return (
      <div className="seller-profile-page">
        <div className="skeleton-loader">
          <div className="skeleton-card skeleton-header" />
          <div className="skeleton-card skeleton-stats" />
          <div className="skeleton-card skeleton-reputation" />
        </div>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="seller-profile-page">
        <div className="error-message">
          {error || 'Failed to load seller profile'}
          <button onClick={() => navigate(-1)} className="back-button">
            Go Back
          </button>
        </div>
      </div>
    )
  }

  const avatarColor = getAvatarColor(wallet)
  const displayName = profile.display_name || 'Anonymous Seller'
  const isRegisteredAgent = profile.registered_agent_role && profile.registered_agent_name
  const effectiveReputation = reputationSummary?.effective_score ?? profile.reputation_score_effective
  const rawReputation = reputationSummary?.raw_score ?? profile.reputation_score_raw
  const totalPurchases = reputationSummary?.total_purchases ?? profile.total_purchases
  const totalEarnedUsdc = formatUsdc(profile.total_usdc_earned_micro)
  const averagePrice = profile.avg_price_usdc ? profile.avg_price_usdc.toFixed(2) : 'N/A'
  const sparklineSource = reputationHistory.length > 0 ? reputationHistory : profile.reputation_history

  // Prepare reputation sparkline data
  const sparklineData = sparklineSource.map((entry) => ({
    score: entry.score_after,
    timestamp: new Date(entry.recorded_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }))

  return (
    <div className="seller-profile-page">
      {/* Section 1: Profile Header */}
      <section className="seller-profile-section seller-profile-header">
        <div className="header-avatar" style={{ backgroundColor: avatarColor }}>
          {displayName.slice(0, 1).toUpperCase()}
        </div>

        <div className="header-info">
          <h1 className="header-name">{displayName}</h1>
          <div className="header-wallet">
            <code>{truncateWallet(wallet)}</code>
            <button
              className="copy-button"
              onClick={() => copyToClipboard(wallet)}
              title="Copy full wallet address"
            >
              📋
            </button>
          </div>

          <div className="header-badges">
            {isRegisteredAgent ? (
              <>
                <span className="badge badge--verified">✓ Verified Agent</span>
                <span className={`badge badge--role badge--role-${profile.registered_agent_role?.toLowerCase()}`}>
                  {profile.registered_agent_role}
                </span>
              </>
            ) : (
              <span className="badge badge--unverified">Unverified Seller</span>
            )}
          </div>
        </div>

        <div className={`header-reputation ${getReputationBadgeClass(effectiveReputation)}`}>
          <div className="reputation-score">{effectiveReputation}</div>
          <div className="reputation-label">Score</div>
        </div>
      </section>

      {/* Section 2: Stats Grid */}
      <section className="seller-profile-section seller-profile-stats">
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Insights Sold</div>
            <div className="stat-value">{totalPurchases}</div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Total USDC Earned</div>
            <div className="stat-value">${totalEarnedUsdc}</div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Average Price</div>
            <div className="stat-value">${averagePrice}</div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Days Active</div>
            <div className="stat-value">
              {profile.first_listing_date
                ? Math.floor(
                    (Date.now() - new Date(profile.first_listing_date).getTime()) /
                      (1000 * 60 * 60 * 24),
                  )
                : '0'}
            </div>
          </div>
        </div>
      </section>

      {/* Section 2b: Earnings Overview */}
      <section className="seller-profile-section seller-profile-earnings">
        <h2 className="section-title">Earnings Overview</h2>
        <div className="earnings-grid">
          <article className="earnings-card earnings-card--primary">
            <span className="earnings-label">Total Earned</span>
            <strong>${totalEarnedUsdc}</strong>
            <p>Verified from seller profile revenue totals and aligned to purchase activity.</p>
          </article>

          <article className="earnings-card">
            <span className="earnings-label">Average Sale</span>
            <strong>${averagePrice}</strong>
            <p>Helpful for spotting how the seller prices insights over time.</p>
          </article>

          <article className="earnings-card">
            <span className="earnings-label">Latest Purchase</span>
            <strong>{profile.last_purchase_date ? new Date(profile.last_purchase_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'None'}</strong>
            <p>Most recent on-chain purchase date from the seller profile payload.</p>
          </article>
        </div>
      </section>

      {/* Section 3: Reputation Panel */}
      <section className="seller-profile-section seller-profile-reputation">
        <h2 className="section-title">Reputation History</h2>

        <div className="reputation-panel">
          <div className="reputation-score-display">
            <div className="score-circle" style={{ borderColor: avatarColor }}>
              <div className={getReputationBadgeClass(profile.reputation_score_effective)}>
                {profile.reputation_score_effective}
              </div>
            </div>
            <div className="score-details">
              <div className="score-detail-item">
                <span className="detail-label">Effective Score:</span>
                <span className="detail-value">{profile.reputation_score_effective}/100</span>
              </div>
              <div className="score-detail-item">
                <span className="detail-label">Raw Score:</span>
                <span className="detail-value">{rawReputation}</span>
              </div>
              {profile.decay_info?.decay_points_applied !== undefined &&
                profile.decay_info.decay_points_applied > 0 && (
                  <div className="score-detail-item decay-warning">
                    <span className="detail-label">Decay Applied:</span>
                    <span className="detail-value">-{profile.decay_info.decay_points_applied} points</span>
                  </div>
                )}
            </div>
          </div>

          {/* Progress Bar with Thresholds */}
          <div className="progress-bar-container">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{
                  width: `${Math.min(profile.reputation_score_effective / 100, 1) * 100}%`,
                }}
              />
            </div>
            <div className="threshold-markers">
              <div className="threshold" style={{ left: '50%' }} title="Trust threshold">
                <span>50</span>
              </div>
              <div className="threshold" style={{ left: '70%' }} title="High tier threshold">
                <span>70</span>
              </div>
            </div>
          </div>

          {/* Sparkline Chart */}
          {sparklineData.length > 0 ? (
            <div className="sparkline-container">
              <h3 className="sparkline-title">Score Trend (Last 20 Updates)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={sparklineData}>
                  <defs>
                    <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={avatarColor} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={avatarColor} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#fff',
                      border: `2px solid ${avatarColor}`,
                      borderRadius: '8px',
                    }}
                    formatter={(value) => [`Score: ${value}`, 'Reputation']}
                  />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke={avatarColor}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorScore)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="no-history-message">No reputation history available yet</div>
          )}
        </div>
      </section>

      {/* Section 4: Listing History */}
      <section className="seller-profile-section seller-profile-listings">
        <h2 className="section-title">Listing History</h2>

        {listings.length > 0 ? (
          <>
            <div className="listings-table-container">
              <table className="listings-table">
                <thead>
                  <tr>
                    <th>Price</th>
                    <th>Purchases</th>
                    <th>Date</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {listings.map((listing) => {
                    const state = (listing.state || listing.status || '').toLowerCase()
                    const rowClass = state === 'expired' ? 'listing-expired' : state === 'sold' ? 'listing-sold' : ''
                    return (
                      <tr key={listing.listing_id} className={rowClass}>
                        <td className="price-cell">${listing.price_usdc ? listing.price_usdc.toFixed(2) : 'N/A'}</td>
                        <td className="purchases-cell">{listing.purchase_count}</td>
                        <td className="date-cell">
                          {new Date(listing.timestamp_iso).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                          })}
                        </td>
                        <td className="action-cell">
                          {state === 'sold' && <span className="insight-state-pill insight-state-pill--sold">✓ Sold</span>}
                          {state === 'expired' && <span className="insight-state-pill insight-state-pill--expired">⏰ Expired</span>}
                          <button className="view-button" title={`View listing ${listing.listing_id}`}>
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                  className="pagination-button"
                >
                  ← Previous
                </button>
                <span className="pagination-info">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                  className="pagination-button"
                >
                  Next →
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="no-data-message">No listings found for this seller</div>
        )}
      </section>

      {/* Section 4b: Purchase History */}
      <section className="seller-profile-section seller-profile-purchases">
        <h2 className="section-title">Purchase History</h2>

        {purchaseHistory.length > 0 ? (
          <div className="purchase-history-list">
            {purchaseHistory.map((purchase, index) => (
              <article key={`${purchase.buyer_wallet}-${purchase.listing_id}-${index}`} className="purchase-history-item">
                <div className="purchase-history-main">
                  <strong>{truncateWallet(purchase.buyer_wallet)}</strong>
                  <span>Listing {purchase.listing_id}</span>
                </div>
                <div className="purchase-history-meta">
                  <span>Round {purchase.purchase_round ?? 'N/A'}</span>
                  <span>
                    {purchase.purchase_approx_date
                      ? new Date(purchase.purchase_approx_date).toLocaleDateString('en-US', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })
                      : 'Date unavailable'}
                  </span>
                </div>
              </article>
            ))}

            {purchaseNote && <p className="purchase-history-note">{purchaseNote}</p>}
          </div>
        ) : (
          <div className="no-data-message">
            No purchase history available yet
            {purchaseNote ? <p>{purchaseNote}</p> : null}
          </div>
        )}
      </section>

      {/* Section 5: Agent Evaluations */}
      <section className="seller-profile-section seller-profile-evaluations">
        <h2 className="section-title">Agent Evaluation History</h2>

        {profile.evaluations && profile.evaluations.length > 0 ? (
          <div className="evaluations-table-container">
            <table className="evaluations-table">
              <thead>
                <tr>
                  <th>Quality</th>
                  <th>Relevance</th>
                  <th>Total Score</th>
                  <th>Decision</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {profile.evaluations.slice(0, 10).map((eval_record) => (
                  <tr key={eval_record.evaluation_id}>
                    <td className="score-cell">{eval_record.quality_score}</td>
                    <td className="score-cell">{eval_record.relevance_score}</td>
                    <td className="score-cell">
                      <strong>{eval_record.total_score}</strong>
                    </td>
                    <td className="decision-cell">
                      <span
                        className={`decision-badge decision-${eval_record.decision?.toLowerCase()}`}
                      >
                        {eval_record.decision}
                      </span>
                    </td>
                    <td className="date-cell">
                      {new Date(eval_record.created_at).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="no-data-message">No evaluation history available yet</div>
        )}
      </section>

      {/* Section 6: Trust Summary */}
      <section className="seller-profile-section seller-profile-trust-summary">
        <h2 className="section-title">Trust Summary</h2>

        {profile.trust_summary ? (
          <div className="trust-summary-box">
            <p>{profile.trust_summary}</p>
          </div>
        ) : (
          <div className="no-data-message">Trust summary not yet available</div>
        )}
      </section>
    </div>
  )
}

export default SellerProfilePage


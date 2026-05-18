import React, { useMemo, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../utils/api'
import type { SellerProfileResponse } from '../types'
import './SellerCard.css'

// Module-level cache shared across all SellerCard instances
const sellerCardCache = new Map<string, { profile: SellerProfileResponse; fetchedAt: number }>()

interface SellerCardProps {
  wallet: string
  expanded?: boolean // For expanded mode in InsightDetail showing trust summary
}

/**
 * Deterministic avatar color from wallet hash
 */
function getAvatarColor(wallet: string): string {
  const hex = wallet.slice(0, 6)
  const hue = (parseInt(hex, 16) % 360)
  return `hsl(${hue}, 70%, 60%)`
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
 * Get reputation badge color
 */
function getReputationBadgeClass(score: number): string {
  if (score >= 80) return 'reputation-badge reputation-badge--excellent'
  if (score >= 70) return 'reputation-badge reputation-badge--good'
  if (score >= 50) return 'reputation-badge reputation-badge--fair'
  return 'reputation-badge reputation-badge--poor'
}

/**
 * Reusable seller card component for displaying seller previews
 * Uses module-level cache to prevent duplicate API calls for the same seller
 */
export const SellerCard: React.FC<SellerCardProps> = ({ wallet, expanded = false }) => {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<SellerProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Check if this is a demo wallet (from demo data or testing)
  const isDemoWallet = wallet.includes('...') || wallet.startsWith('MKT') || wallet.startsWith('EQL')

  const fetchProfile = useMemo(() => {
    return async () => {
      // Skip fetching for demo wallets - show mock profile instead
      if (isDemoWallet) {
        const mockProfile: SellerProfileResponse = {
          seller_wallet: wallet,
          display_name: wallet.replace('...', ' '),
          seller_stats: {
            seller_wallet: wallet,
            total_purchases: 0,
            total_usdc_earned_micro: 0,
            avg_price_usdc: null,
            first_listing_date: null,
            last_purchase_date: null,
            recent_evaluations_avg_score: null,
            display_name: wallet.replace('...', ' '),
            registered_agent_name: null,
            registered_agent_role: null,
            registered_at_round: null,
            trust_summary: 'Demo seller profile',
          },
          reputation_score_effective: 0,
          reputation_score_raw: 0,
          decay_info: {
            last_updated_at: null,
            decay_rate: null,
            decay_points_applied: 0,
          },
          registered_agent_name: null,
          registered_agent_role: null,
          registered_at_round: null,
          reputation_history: [],
          trust_summary: 'Demo seller profile',
        }
        setProfile(mockProfile)
        setLoading(false)
        return
      }

      // Check cache first for real wallets
      const cached = sellerCardCache.get(wallet)
      if (cached && Date.now() - cached.fetchedAt < 30000) {
        // Cache hit - within 30 seconds
        setProfile(cached.profile)
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        setError(null)
        const fetchedProfile = await api.sellerProfile(wallet)
        if (fetchedProfile) {
          sellerCardCache.set(wallet, { profile: fetchedProfile, fetchedAt: Date.now() })
          setProfile(fetchedProfile)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load seller profile')
      } finally {
        setLoading(false)
      }
    }
  }, [wallet, isDemoWallet])

  useEffect(() => {
    fetchProfile()
  }, [wallet, fetchProfile, isDemoWallet])

  if (loading) {
    return (
      <div className={`seller-card ${expanded ? 'seller-card--expanded' : ''}`}>
        <div className="seller-card--loading">Loading seller profile...</div>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className={`seller-card ${expanded ? 'seller-card--expanded' : ''}`}>
        <div className="seller-card--error">Unable to load seller profile</div>
      </div>
    )
  }

  const avatarColor = getAvatarColor(wallet)
  const displayName = profile.display_name || 'Anonymous Seller'
  const isRegisteredAgent = profile.registered_agent_role && profile.registered_agent_name

  if (expanded) {
    // Expanded mode for InsightDetail page - show full profile details
    return (
      <div className="seller-card seller-card--expanded">
        <div className="seller-card-expanded__header">
          <div
            className="seller-card-expanded__avatar"
            style={{ backgroundColor: avatarColor }}
            title={wallet}
          >
            {displayName.slice(0, 1).toUpperCase()}
          </div>
          <div className="seller-card-expanded__info">
            <h3 className="seller-card-expanded__name">{displayName}</h3>
            <p className="seller-card-expanded__wallet">{truncateWallet(wallet)}</p>
            {isRegisteredAgent && (
              <span className="seller-card-expanded__agent-badge">
                ✓ {profile.registered_agent_role}
              </span>
            )}
          </div>
          <div className={getReputationBadgeClass(profile.reputation_score_effective)}>
            {profile.reputation_score_effective}
          </div>
        </div>

        <div className="seller-card-expanded__stats">
          <div className="stat">
            <span className="stat__label">Total Sales</span>
            <span className="stat__value">{profile.total_purchases}</span>
          </div>
          <div className="stat">
            <span className="stat__label">Total Earnings</span>
            <span className="stat__value">${formatUsdc(profile.total_usdc_earned_micro)}</span>
          </div>
          <div className="stat">
            <span className="stat__label">Avg Price</span>
            <span className="stat__value">
              ${profile.avg_price_usdc ? profile.avg_price_usdc.toFixed(2) : 'N/A'}
            </span>
          </div>
          <div className="stat">
            <span className="stat__label">Days Active</span>
            <span className="stat__value">
              {profile.first_listing_date
                ? Math.floor(
                    (Date.now() - new Date(profile.first_listing_date).getTime()) /
                      (1000 * 60 * 60 * 24),
                  )
                : '0'}
            </span>
          </div>
        </div>

        {profile.trust_summary && (
          <div className="seller-card-expanded__trust-summary">
            <h4>Trust Summary</h4>
            <p>{profile.trust_summary}</p>
          </div>
        )}

        <button
          className="seller-card-expanded__view-button"
          onClick={() => navigate(`/sellers/${wallet}`)}
        >
          View Full Profile →
        </button>
      </div>
    )
  }

  // Compact mode - minimal display
  return (
    <div
      className="seller-card"
      onClick={() => navigate(`/sellers/${wallet}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          navigate(`/sellers/${wallet}`)
        }
      }}
    >
      <div
        className="seller-card__avatar"
        style={{ backgroundColor: avatarColor }}
        title={wallet}
      >
        {displayName.slice(0, 1).toUpperCase()}
      </div>

      <div className="seller-card__info">
        <div className="seller-card__name">{displayName}</div>
        {profile.registered_agent_role && (
          <div className="seller-card__role">{profile.registered_agent_role}</div>
        )}
      </div>

      <div className={getReputationBadgeClass(profile.reputation_score_effective)}>
        {profile.reputation_score_effective}
      </div>

      <span className="seller-card__link">→</span>
    </div>
  )
}

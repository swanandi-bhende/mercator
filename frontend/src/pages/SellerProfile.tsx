import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { api } from '../utils/api'
import type { LayoutOutletContext } from '../components/Layout'
import { useOutletContext } from 'react-router-dom'

interface ReputationData {
  wallet: string
  effective_score: number
  raw_score: number
  decay_points_applied: number
  rounds_since_last_purchase: number
  rounds_until_decay_starts: number
  total_purchases: number
  last_purchase_round: number
  last_purchase_approx_date: string
}

interface PurchaseRecord {
  buyer_wallet: string
  listing_id: string
  purchase_round: number
  purchase_approx_date: string
}

export default function SellerProfilePage() {
  const navigate = useNavigate()
  const { latestWsEvent } = useOutletContext<LayoutOutletContext>()
  const { buyerWallet } = useAppContext()
  const { wallet } = useParams<{ wallet: string }>()

  const [reputation, setReputation] = useState<ReputationData | null>(null)
  const [purchaseHistory, setPurchaseHistory] = useState<PurchaseRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reputationCacheRef = useRef<Map<string, { data: ReputationData; fetchedAt: number }>>(
    new Map(),
  )

  const fetchReputation = async (sellerWallet: string) => {
    if (!sellerWallet) return

    const cached = reputationCacheRef.current.get(sellerWallet)
    if (cached && Date.now() - cached.fetchedAt < 60000) {
      setReputation(cached.data)
      setError(null)
      return
    }

    try {
      const data = await api.get<ReputationData>(`/sellers/${sellerWallet}/reputation`)
      if (data && data.wallet) {
        reputationCacheRef.current.set(sellerWallet, {
          data,
          fetchedAt: Date.now(),
        })
        setReputation(data)
        setError(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reputation')
      setReputation(null)
    }
  }

  const fetchPurchaseHistory = async (sellerWallet: string) => {
    if (!sellerWallet) return

    try {
      const data = await api.get<{ purchase_history: PurchaseRecord[] }>(
        `/sellers/${sellerWallet}/purchase_history`,
      )
      if (data && Array.isArray(data.purchase_history)) {
        setPurchaseHistory(data.purchase_history)
      }
    } catch {
      setPurchaseHistory([])
    }
  }

  useEffect(() => {
    if (!wallet) {
      setError('No seller wallet provided')
      setLoading(false)
      return
    }

    setLoading(true)
    Promise.all([fetchReputation(wallet), fetchPurchaseHistory(wallet)]).finally(() => {
      setLoading(false)
    })
  }, [wallet])

  // Listen for reputation updates via WebSocket
  useEffect(() => {
    if (!wallet || !latestWsEvent) return

    if (latestWsEvent.event_type === 'reputation_updated') {
      const payload = latestWsEvent.payload as Record<string, unknown>
      if (String(payload.wallet) === wallet) {
        // Invalidate cache and refetch
        reputationCacheRef.current.delete(wallet)
        void fetchReputation(wallet)
        void fetchPurchaseHistory(wallet)
      }
    }
  }, [latestWsEvent, wallet])

  const getScoreBadgeColor = (score: number): string => {
    if (score >= 70) return 'reputation-badge--green'
    if (score >= 50) return 'reputation-badge--yellow'
    return 'reputation-badge--red'
  }

  const daysUntilDecay = reputation
    ? (reputation.rounds_until_decay_starts * 4.5) / 86400
    : 0

  return (
    <div className="seller-profile-page">
      <header className="seller-profile-header">
        <button onClick={() => navigate(-1)} className="seller-profile-back-btn">
          ← Back
        </button>
        <h1>Seller Profile</h1>
        <p className="seller-profile-wallet">{wallet}</p>
      </header>

      {loading && (
        <div className="seller-profile-loading">
          <p>Loading seller reputation...</p>
        </div>
      )}

      {error && !loading && (
        <div className="seller-profile-error">
          <p>Error: {error}</p>
          <button onClick={() => wallet && fetchReputation(wallet)}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && reputation && (
        <main className="seller-profile-content">
          <section className="reputation-breakdown-panel">
            <h2>Reputation Breakdown</h2>

            <div className="reputation-score-display">
              <div className={`reputation-badge ${getScoreBadgeColor(reputation.effective_score)}`}>
                <span className="reputation-score-number">{reputation.effective_score}</span>
                <span className="reputation-score-label">Score</span>
              </div>

              <div className="reputation-progress-container">
                <div className="reputation-progress-bar">
                  <div
                    className="reputation-progress-fill"
                    style={{
                      width: `${Math.min((reputation.effective_score / 100) * 100, 100)}%`,
                    }}
                  ></div>
                </div>
                <p className="reputation-progress-label">
                  {reputation.effective_score} of 100
                </p>
              </div>
            </div>

            <div className="reputation-details">
              <p>
                <strong>Raw score:</strong> {reputation.raw_score} — <strong>Decay applied:</strong>{' '}
                {reputation.decay_points_applied} points
              </p>
              <p className="reputation-decay-info">
                Decay starts in approximately <strong>{daysUntilDecay.toFixed(1)} days</strong>
              </p>
            </div>

            <div className="reputation-stats">
              <div className="stat-card">
                <span className="stat-label">Total Purchases</span>
                <span className="stat-value">{reputation.total_purchases}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Last Purchase</span>
                <span className="stat-value">
                  {new Date(reputation.last_purchase_approx_date).toLocaleDateString()}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Rounds Since Last</span>
                <span className="stat-value">{reputation.rounds_since_last_purchase}</span>
              </div>
            </div>
          </section>

          <section className="purchase-history-panel">
            <h2>Recent Purchases</h2>
            {purchaseHistory.length === 0 ? (
              <p className="purchase-history-empty">No purchase history yet</p>
            ) : (
              <div className="purchase-history-table">
                <table>
                  <thead>
                    <tr>
                      <th>Buyer Wallet</th>
                      <th>Listing ID</th>
                      <th>Purchase Date</th>
                      <th>Round</th>
                    </tr>
                  </thead>
                  <tbody>
                    {purchaseHistory.map((record, idx) => (
                      <tr key={idx} className="purchase-record">
                        <td className="purchase-wallet" title={record.buyer_wallet}>
                          {record.buyer_wallet.slice(0, 12)}...
                        </td>
                        <td className="purchase-listing">{record.listing_id}</td>
                        <td className="purchase-date">
                          {new Date(record.purchase_approx_date).toLocaleDateString()}
                        </td>
                        <td className="purchase-round">{record.purchase_round}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="seller-profile-actions">
            <button onClick={() => navigate(`/discover?seller=${wallet}`)}>
              View Seller's Listings
            </button>
            {buyerWallet && (
              <button onClick={() => navigate('/checkout')}>
                Search & Buy from This Seller
              </button>
            )}
          </section>
        </main>
      )}

      <style>{`
        .seller-profile-page {
          min-height: 100vh;
          background: linear-gradient(135deg, #f5f5f7 0%, #ffffff 100%);
          padding: 20px;
        }

        .seller-profile-header {
          max-width: 900px;
          margin: 0 auto 40px;
          display: flex;
          align-items: center;
          gap: 20px;
          border-bottom: 1px solid #e0e0e0;
          padding-bottom: 20px;
        }

        .seller-profile-back-btn {
          padding: 8px 12px;
          background: #f0f0f0;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-size: 14px;
          transition: background 0.2s;
        }

        .seller-profile-back-btn:hover {
          background: #e0e0e0;
        }

        .seller-profile-header h1 {
          margin: 0;
          font-size: 28px;
          flex: 1;
        }

        .seller-profile-wallet {
          margin: 0;
          font-size: 14px;
          color: #666;
          font-family: monospace;
        }

        .seller-profile-loading,
        .seller-profile-error {
          max-width: 900px;
          margin: 0 auto;
          padding: 40px;
          text-align: center;
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        }

        .seller-profile-error {
          border-left: 4px solid #d32f2f;
        }

        .seller-profile-error button {
          margin-top: 20px;
          padding: 10px 20px;
          background: #d32f2f;
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-size: 14px;
        }

        .seller-profile-content {
          max-width: 900px;
          margin: 0 auto;
          display: grid;
          gap: 40px;
        }

        .reputation-breakdown-panel {
          background: white;
          border-radius: 12px;
          padding: 40px;
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        }

        .reputation-breakdown-panel h2 {
          margin: 0 0 30px 0;
          font-size: 22px;
          border-bottom: 2px solid #f0f0f0;
          padding-bottom: 15px;
        }

        .reputation-score-display {
          display: grid;
          grid-template-columns: 120px 1fr;
          gap: 40px;
          margin-bottom: 30px;
          align-items: center;
        }

        .reputation-badge {
          width: 120px;
          height: 120px;
          border-radius: 50%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          font-weight: bold;
          color: white;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .reputation-badge--green {
          background: linear-gradient(135deg, #4caf50, #45a049);
        }

        .reputation-badge--yellow {
          background: linear-gradient(135deg, #ff9800, #fb8c00);
        }

        .reputation-badge--red {
          background: linear-gradient(135deg, #f44336, #d32f2f);
        }

        .reputation-score-number {
          font-size: 40px;
          line-height: 1;
        }

        .reputation-score-label {
          font-size: 12px;
          margin-top: 8px;
          opacity: 0.9;
        }

        .reputation-progress-container {
          flex: 1;
        }

        .reputation-progress-bar {
          height: 24px;
          background: #e0e0e0;
          border-radius: 12px;
          overflow: hidden;
          margin-bottom: 8px;
        }

        .reputation-progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #4caf50, #45a049);
          transition: width 0.3s ease;
        }

        .reputation-progress-label {
          margin: 0;
          font-size: 13px;
          color: #666;
        }

        .reputation-details {
          margin: 30px 0;
          padding: 20px;
          background: #f9f9f9;
          border-left: 4px solid #2196f3;
          border-radius: 4px;
        }

        .reputation-details p {
          margin: 8px 0;
          font-size: 14px;
          line-height: 1.6;
        }

        .reputation-decay-info {
          color: #1976d2;
          font-weight: 500;
        }

        .reputation-stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 20px;
          margin-top: 30px;
        }

        .stat-card {
          padding: 20px;
          background: #f5f5f5;
          border-radius: 8px;
          text-align: center;
          border: 1px solid #e0e0e0;
        }

        .stat-label {
          display: block;
          font-size: 12px;
          text-transform: uppercase;
          color: #999;
          letter-spacing: 0.5px;
          margin-bottom: 8px;
        }

        .stat-value {
          display: block;
          font-size: 24px;
          font-weight: bold;
          color: #1976d2;
        }

        .purchase-history-panel {
          background: white;
          border-radius: 12px;
          padding: 40px;
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        }

        .purchase-history-panel h2 {
          margin: 0 0 30px 0;
          font-size: 22px;
          border-bottom: 2px solid #f0f0f0;
          padding-bottom: 15px;
        }

        .purchase-history-empty {
          text-align: center;
          color: #999;
          padding: 40px 20px;
          font-style: italic;
        }

        .purchase-history-table {
          overflow-x: auto;
        }

        .purchase-history-table table {
          width: 100%;
          border-collapse: collapse;
          font-size: 14px;
        }

        .purchase-history-table thead {
          background: #f5f5f5;
          border-bottom: 2px solid #e0e0e0;
        }

        .purchase-history-table th {
          padding: 12px;
          text-align: left;
          font-weight: 600;
          color: #333;
        }

        .purchase-history-table td {
          padding: 12px;
          border-bottom: 1px solid #e0e0e0;
        }

        .purchase-record:hover {
          background: #f9f9f9;
        }

        .purchase-wallet {
          font-family: monospace;
          font-size: 12px;
          color: #666;
        }

        .purchase-listing {
          font-weight: 500;
          color: #1976d2;
        }

        .purchase-date {
          color: #666;
        }

        .purchase-round {
          color: #999;
          font-size: 12px;
        }

        .seller-profile-actions {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 15px;
          padding: 20px 0;
        }

        .seller-profile-actions button {
          padding: 12px 20px;
          background: #1976d2;
          color: white;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }

        .seller-profile-actions button:hover {
          background: #1565c0;
        }

        @media (max-width: 768px) {
          .seller-profile-header {
            flex-direction: column;
            align-items: flex-start;
          }

          .reputation-score-display {
            grid-template-columns: 1fr;
            gap: 20px;
          }

          .reputation-badge {
            margin: 0 auto;
          }

          .reputation-stats {
            grid-template-columns: 1fr;
          }

          .purchase-history-table {
            font-size: 12px;
          }

          .purchase-history-table th,
          .purchase-history-table td {
            padding: 8px;
          }
        }
      `}</style>
    </div>
  )
}

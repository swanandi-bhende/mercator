import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { useAppContext } from '../context/AppContext'
import { ApiError, api } from '../utils/api'
import type { AtomicSubscribeResponse, FeeConfigResponse, SubscriptionStatusResponse } from '../types'

function explorerUrl(txId?: string) {
  return txId ? `https://lora.algokit.io/testnet/tx/${txId}` : ''
}

function formatMicroUsdc(amountMicro?: number) {
  if (typeof amountMicro !== 'number') return '--'
  return `${(amountMicro / 1_000_000).toFixed(2)} USDC`
}

export default function SubscriptionManagerPage() {
  const { buyerWallet, setBuyerWallet } = useAppContext()
  const [walletInput, setWalletInput] = useState(buyerWallet ?? '')
  const [months, setMonths] = useState(1)
  const [status, setStatus] = useState<SubscriptionStatusResponse | null>(null)
  const [feeConfig, setFeeConfig] = useState<FeeConfigResponse | null>(null)
  const [atomicResult, setAtomicResult] = useState<AtomicSubscribeResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [loadingFeeConfig, setLoadingFeeConfig] = useState(false)
  const [subscribing, setSubscribing] = useState(false)
  const [atomicSupported, setAtomicSupported] = useState(true)

  const paymentTxId = atomicResult?.data?.payment_tx_id ?? ''
  const subscriptionTxId = atomicResult?.data?.subscription_tx_id ?? ''
  const paymentExplorerUrl = explorerUrl(paymentTxId)
  const subscriptionExplorerUrl = explorerUrl(subscriptionTxId)
  const monthlyRateDisplay = feeConfig?.fee_rate_display || `${((feeConfig?.fee_rate_bps ?? 500) / 100).toFixed(1)}%`
  const monthlyRateMicro = feeConfig?.fee_rate_bps ? Math.round((feeConfig.fee_rate_bps / 10000) * 1_000_000) : 50000000
  const isActive = Boolean(status?.active)

  const syncWallet = (nextWallet: string) => {
    setWalletInput(nextWallet)
    setBuyerWallet(nextWallet)
  }

  const loadStatus = async (wallet = walletInput) => {
    const trimmed = wallet.trim()
    if (!trimmed) {
      setStatus(null)
      return
    }

    setLoadingStatus(true)
    try {
      const response = await api.subscriptionStatus(trimmed)
      setStatus(response)
      setMessage(null)
      setError(null)
    } catch (loadError) {
      setStatus(null)
      setError(loadError instanceof Error ? loadError.message : 'Unable to load subscription status')
    } finally {
      setLoadingStatus(false)
    }
  }

  const loadFeeConfig = async () => {
    setLoadingFeeConfig(true)
    try {
      const response = await api.feeConfig()
      setFeeConfig(response)
    } catch (loadError) {
      setFeeConfig(null)
      setError(loadError instanceof Error ? loadError.message : 'Unable to load fee configuration')
    } finally {
      setLoadingFeeConfig(false)
    }
  }

  useEffect(() => {
    void loadFeeConfig()
  }, [])

  useEffect(() => {
    if (buyerWallet) {
      setWalletInput(buyerWallet)
      void loadStatus(buyerWallet)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buyerWallet])

  const handleStandardSubscribe = async () => {
    const trimmed = walletInput.trim()
    if (!trimmed) {
      setError('Enter a buyer wallet before subscribing.')
      return
    }

    setSubscribing(true)
    setError(null)
    setMessage(null)
    try {
      const response = await api.subscribe(trimmed, months)
      setBuyerWallet(trimmed)
      await loadStatus(trimmed)
      setAtomicResult({
        success: true,
        data: {
          payment_tx_id: response.payment_tx_id || response.tx_id,
          subscription_tx_id: response.subscription_tx_id || response.tx_id,
          months,
          buyer_wallet: trimmed,
        },
      })
      setMessage('Subscription submitted successfully.')
    } catch (subscribeError) {
      setError(subscribeError instanceof Error ? subscribeError.message : 'Subscription failed')
    } finally {
      setSubscribing(false)
    }
  }

  const handleAtomicSubscribe = async () => {
    const trimmed = walletInput.trim()
    if (!trimmed) {
      setError('Enter a buyer wallet before using atomic subscribe.')
      return
    }

    setSubscribing(true)
    setError(null)
    setMessage(null)
    try {
      const response = await api.subscribeAtomically(trimmed, months)
      setBuyerWallet(trimmed)
      await loadStatus(trimmed)
      setAtomicResult(response)
      setMessage('Atomic subscribe completed successfully.')
    } catch (subscribeError) {
      const originalError = subscribeError instanceof ApiError ? subscribeError.originalError : subscribeError
      if (axios.isAxiosError(originalError) && [404, 405].includes(originalError.response?.status || 0)) {
        setAtomicSupported(false)
        setMessage('Atomic endpoint is unavailable here. Falling back to standard subscribe.')
        await handleStandardSubscribe()
        return
      }

      if (subscribeError instanceof ApiError && subscribeError.userMessage.toLowerCase().includes('atomic')) {
        setAtomicSupported(false)
      }
      setError(subscribeError instanceof Error ? subscribeError.message : 'Atomic subscription failed')
    } finally {
      setSubscribing(false)
    }
  }

  const handleRefresh = async () => {
    await Promise.all([loadFeeConfig(), loadStatus()])
  }

  const statusLabel = useMemo(() => {
    if (loadingStatus) return 'Refreshing status...'
    if (status?.active) return 'Active'
    return 'Inactive'
  }, [loadingStatus, status?.active])

  return (
    <div className="subscription-page">
      <section className="subscription-hero">
        <div className="home-wrap subscription-shell">
          <article className="subscription-intro-card">
            <p className="home-kicker">Subscription Manager</p>
            <h1>Manage buyer access, monthly fee config, and atomic subscribe flow.</h1>
            <p>
              Confirm the current subscription state, inspect the contract fee configuration, and
              subscribe either through the standard path or the atomic grouped route when available.
            </p>
            <div className="subscription-inline-actions">
              <button className="subscription-btn subscription-btn--primary" onClick={handleRefresh}>
                Refresh Status
              </button>
              <button className="subscription-btn subscription-btn--secondary" onClick={() => loadStatus()}>
                Check Buyer Status
              </button>
            </div>
          </article>

          <article className={`subscription-status-card ${isActive ? 'is-active' : ''}`}>
            <div className="subscription-card-heading">
              <div>
                <p className="home-kicker">Subscribe Status</p>
                <h2>{statusLabel}</h2>
              </div>
              {isActive && <span className="subscription-pill">✓ Active</span>}
            </div>

            <label className="subscription-input-group">
              <span>Buyer wallet</span>
              <input
                value={walletInput}
                onChange={(event) => syncWallet(event.target.value)}
                placeholder="Enter Algorand buyer wallet"
              />
            </label>

            <div className="subscription-status-grid">
              <div>
                <span>Expiry round</span>
                <strong>{status?.expiry_round || '--'}</strong>
              </div>
              <div>
                <span>Approx expiry</span>
                <strong>{status?.expiry_approx_date || '--'}</strong>
              </div>
              <div>
                <span>Months remaining</span>
                <strong>{typeof status?.months_remaining === 'number' ? status.months_remaining.toFixed(2) : '--'}</strong>
              </div>
              <div>
                <span>Months paid</span>
                <strong>{status?.total_months_paid ?? '--'}</strong>
              </div>
            </div>

            <p className="subscription-status-meta">
              {status?.active
                ? `Source: ${status.source_type || 'subscription contract'} · ${formatMicroUsdc(status.total_usdc_paid_micro)} paid total`
                : 'No active subscription detected for the current wallet.'}
            </p>
          </article>

          <article className="subscription-fee-card">
            <p className="home-kicker">Fee Config</p>
            <h2>Contract pricing and treasury config</h2>
            <div className="subscription-fee-grid">
              <div>
                <span>Fee rate</span>
                <strong>{monthlyRateDisplay}</strong>
              </div>
              <div>
                <span>Monthly price</span>
                <strong>{formatMicroUsdc(monthlyRateMicro)}</strong>
              </div>
              <div>
                <span>App ID</span>
                <strong>{feeConfig?.app_id || '--'}</strong>
              </div>
              <div>
                <span>USDC asset ID</span>
                <strong>{feeConfig?.usdc_asset_id || '--'}</strong>
              </div>
              <div className="subscription-fee-grid__wide">
                <span>Treasury address</span>
                <strong>{feeConfig?.treasury_address || 'Unavailable'}</strong>
              </div>
              <div>
                <span>Total fees collected</span>
                <strong>{formatMicroUsdc(feeConfig?.total_fees_collected)}</strong>
              </div>
            </div>
            <p className="subscription-status-meta">
              {loadingFeeConfig ? 'Loading fee configuration...' : feeConfig?.success ? 'Fee config loaded from /fee_config.' : feeConfig?.error || 'Fee config unavailable.'}
            </p>
          </article>

          <article className="subscription-action-card">
            <p className="home-kicker">Subscribe Flow</p>
            <h2>{atomicSupported ? 'Choose standard or atomic subscribe' : 'Standard subscribe only'}</h2>
            <div className="subscription-action-controls">
              <label className="subscription-input-group">
                <span>Months</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={months}
                  onChange={(event) => setMonths(Number(event.target.value) || 1)}
                />
              </label>
              <div className="subscription-action-buttons">
                <button className="subscription-btn subscription-btn--primary" onClick={handleAtomicSubscribe} disabled={subscribing}>
                  {subscribing ? 'Processing...' : 'Atomic Subscribe'}
                </button>
                <button className="subscription-btn subscription-btn--secondary" onClick={handleStandardSubscribe} disabled={subscribing}>
                  {subscribing ? 'Processing...' : 'Standard Subscribe'}
                </button>
              </div>
            </div>
            <p className="subscription-status-meta">
              Atomic subscribe posts to /api/v1/subscribe_atomically when available. If the route is unavailable, the page falls back to the standard subscribe flow.
            </p>
            {atomicResult?.data && (
              <div className="subscription-atomic-result">
                <h3>Latest atomic receipt</h3>
                <div className="subscription-atomic-grid">
                  <div>
                    <span>Payment tx</span>
                    <strong>{atomicResult.data.payment_tx_id || '--'}</strong>
                    {paymentExplorerUrl && (
                      <a href={paymentExplorerUrl} target="_blank" rel="noreferrer">Open payment explorer</a>
                    )}
                  </div>
                  <div>
                    <span>Subscription tx</span>
                    <strong>{atomicResult.data.subscription_tx_id || '--'}</strong>
                    {subscriptionExplorerUrl && (
                      <a href={subscriptionExplorerUrl} target="_blank" rel="noreferrer">Open subscription explorer</a>
                    )}
                  </div>
                  <div>
                    <span>Confirmed round</span>
                    <strong>{atomicResult.data.confirmed_round || '--'}</strong>
                  </div>
                  <div>
                    <span>Group ID</span>
                    <strong>{atomicResult.data.group_id || '--'}</strong>
                  </div>
                </div>
              </div>
            )}
            {message && <p className="subscription-success">{message}</p>}
            {error && <p className="subscription-error">{error}</p>}
          </article>
        </div>
      </section>
    </div>
  )
}

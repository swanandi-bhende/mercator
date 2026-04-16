import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { api, ApiError } from '../utils/api'
import type { DemoPurchaseResponse } from '../types'

type CheckoutStageKey =
  | 'validating_wallet'
  | 'checking_approval'
  | 'simulating_payment'
  | 'submitting_x402'
  | 'waiting_confirmation'
  | 'finalizing_delivery'

type StageStatus = 'pending' | 'active' | 'done' | 'error'

type CheckoutIssue =
  | 'none'
  | 'consent_rejected'
  | 'wallet_failure'
  | 'insufficient_balance'
  | 'payment_rejected'
  | 'network_failure'
  | 'confirmation_failure'
  | 'escrow_failure'
  | 'delivery_failure'
  | 'other_error'

type DeliveryOutcome = {
  status: 'success' | 'failed'
  heading: string
  body: string
  detail: string
}

function extractTxFromOutput(output: string, kind: 'payment' | 'escrow') {
  const pattern = kind === 'payment' ? /payment=([A-Z0-9]+)/i : /escrow=([A-Z0-9]+)/i
  const match = output.match(pattern)
  return match?.[1] || null
}

function parseListingId(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined
  const normalized = String(value)
  const digits = normalized.match(/\d+/)?.[0]
  if (!digits) return undefined
  const parsed = Number.parseInt(digits, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

const APPROVAL_TEXT = 'I understand this is a paid insight and I approve this transaction.'

const CHECKOUT_STAGES: { key: CheckoutStageKey; label: string; detail: string }[] = [
  {
    key: 'validating_wallet',
    label: 'Validating wallet',
    detail: 'Confirm buyer wallet address and checkout context.',
  },
  {
    key: 'checking_approval',
    label: 'Checking approval',
    detail: 'Verify explicit consent before payment submission.',
  },
  {
    key: 'simulating_payment',
    label: 'Simulating payment',
    detail: 'Run policy and spend checks before moving funds.',
  },
  {
    key: 'submitting_x402',
    label: 'Submitting x402',
    detail: 'Submit approved payment to backend x402 flow.',
  },
  {
    key: 'waiting_confirmation',
    label: 'Waiting for confirmation',
    detail: 'Track transaction and chain-level confirmation.',
  },
  {
    key: 'finalizing_delivery',
    label: 'Finalizing delivery',
    detail: 'Confirm escrow and insight delivery outcome.',
  },
]

function toStageMap(activeStage: CheckoutStageKey | null, failedStage: CheckoutStageKey | null) {
  const map: Record<CheckoutStageKey, StageStatus> = {
    validating_wallet: 'pending',
    checking_approval: 'pending',
    simulating_payment: 'pending',
    submitting_x402: 'pending',
    waiting_confirmation: 'pending',
    finalizing_delivery: 'pending',
  }

  if (!activeStage && !failedStage) {
    return map
  }

  let afterCurrent = false
  for (const stage of CHECKOUT_STAGES) {
    if (failedStage && stage.key === failedStage) {
      map[stage.key] = 'error'
      afterCurrent = true
      continue
    }

    if (activeStage && stage.key === activeStage) {
      map[stage.key] = 'active'
      afterCurrent = true
      continue
    }

    map[stage.key] = afterCurrent ? 'pending' : 'done'
  }

  return map
}

export default function CheckoutPage() {
  const navigate = useNavigate()
  const {
    selectedInsight,
    sellerMetadata,
    buyerWallet,
    hasReviewedEvaluation,
    setBuyerWallet,
    setPaymentState,
    setLastTransactionId,
  } = useAppContext()

  const [walletInput, setWalletInput] = useState(buyerWallet || '')
  const [consentChecked, setConsentChecked] = useState(false)
  const [consentText, setConsentText] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [activeStage, setActiveStage] = useState<CheckoutStageKey | null>(null)
  const [failedStage, setFailedStage] = useState<CheckoutStageKey | null>(null)
  const [issue, setIssue] = useState<CheckoutIssue>('none')
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [submittedTxId, setSubmittedTxId] = useState<string | null>(null)
  const [confirmationState, setConfirmationState] = useState<'idle' | 'submitting' | 'confirming' | 'confirmed' | 'failed'>('idle')
  const [deliveryOutcome, setDeliveryOutcome] = useState<DeliveryOutcome | null>(null)

  const stageMap = useMemo(() => toStageMap(activeStage, failedStage), [activeStage, failedStage])

  if (!selectedInsight) {
    return (
      <div className="checkout-page">
        <section className="checkout-empty">
          <div className="home-wrap">
            <div className="checkout-empty-card">
              <p className="home-kicker">Final Gate</p>
              <h1>No evaluated insight selected.</h1>
              <p>Complete discovery and evaluation before entering checkout approval.</p>
              <button className="checkout-btn checkout-btn--primary" onClick={() => navigate('/discover')}>
                Back to Discover
              </button>
            </div>
          </div>
        </section>
      </div>
    )
  }

  if (!hasReviewedEvaluation) {
    return (
      <div className="checkout-page">
        <section className="checkout-empty">
          <div className="home-wrap">
            <div className="checkout-empty-card">
              <p className="home-kicker">Final Gate</p>
              <h1>Review evaluation before checkout.</h1>
              <p>
                Checkout is only available after insight evaluation review so approval is tied to
                a deliberate decision.
              </p>
              <button className="checkout-btn checkout-btn--primary" onClick={() => navigate('/evaluate')}>
                Go to Evaluation
              </button>
            </div>
          </div>
        </section>
      </div>
    )
  }

  const relevance = selectedInsight.relevance_score ?? 0
  const reputation = sellerMetadata?.reputation ?? selectedInsight.seller_reputation ?? 0
  const rationale =
    selectedInsight.synopsis ||
    sellerMetadata?.rankingReason ||
    'Evaluated insight selected for purchase review.'
  const sellerIdentity = sellerMetadata?.address || selectedInsight.seller_wallet

  const resetRunState = () => {
    setIssue('none')
    setStatusMessage(null)
    setFailedStage(null)
    setSubmittedTxId(null)
    setConfirmationState('idle')
    setDeliveryOutcome(null)
  }

  const failWith = (
    nextIssue: CheckoutIssue,
    stage: CheckoutStageKey,
    message: string,
    opts?: { nothingCharged?: boolean; keepTx?: boolean },
  ) => {
    setIssue(nextIssue)
    setFailedStage(stage)
    setConfirmationState(nextIssue === 'confirmation_failure' ? 'failed' : confirmationState)
    const fullMessage = opts?.nothingCharged ? `${message} Transaction was not submitted and nothing was charged.` : message
    setStatusMessage(fullMessage)
    setPaymentState({ stage: 'failed', error: fullMessage, timestamp: new Date().toLocaleTimeString() })
    if (!opts?.keepTx) {
      setSubmittedTxId(null)
    }
  }

  const deriveOutcome = (response: DemoPurchaseResponse, txId: string | null): DeliveryOutcome => {
    const paymentStatus = response.result?.payment_status
    const escrowStatus = String(response.result?.escrow_status || '').toLowerCase()

    if (!txId) {
      return {
        status: 'failed',
        heading: 'Payment submission did not finalize',
        body: 'x402 submission did not return a transaction id, so confirmation could not be completed.',
        detail: 'Failure type: confirmation',
      }
    }

    if (escrowStatus.includes('fail') || escrowStatus.includes('error')) {
      return {
        status: 'failed',
        heading: 'Payment confirmed but escrow release failed',
        body: 'Funds were submitted, but escrow could not complete release cleanly.',
        detail: 'Failure type: escrow',
      }
    }

    if (!response.final_insight_text?.trim()) {
      return {
        status: 'failed',
        heading: 'Payment confirmed but insight retrieval failed',
        body: 'Transaction confirmed, but content delivery could not be completed.',
        detail: 'Failure type: content retrieval',
      }
    }

    if (typeof paymentStatus === 'object' && paymentStatus?.success === false) {
      return {
        status: 'failed',
        heading: 'Payment submitted but confirmation failed',
        body: String(paymentStatus.error || paymentStatus.message || 'Confirmation failed after submission.'),
        detail: 'Failure type: confirmation',
      }
    }

    return {
      status: 'success',
      heading: 'Payment confirmed and insight delivered',
      body: 'Escrow release and insight delivery are complete. You can proceed to receipt details.',
      detail: 'Escrow and delivery status: success',
    }
  }

  const handleApprovePayment = async () => {
    resetRunState()
    setIsProcessing(true)

    try {
      setActiveStage('validating_wallet')
      setPaymentState({ stage: 'pending', timestamp: new Date().toLocaleTimeString() })
      await new Promise((resolve) => setTimeout(resolve, 200))

      if (walletInput.trim().length < 20) {
        failWith('wallet_failure', 'validating_wallet', 'Wallet validation failed. Enter a valid buyer wallet.', {
          nothingCharged: true,
        })
        return
      }

      setBuyerWallet(walletInput.trim())

      setActiveStage('checking_approval')
      await new Promise((resolve) => setTimeout(resolve, 180))
      if (!(consentChecked && consentText.trim() === APPROVAL_TEXT)) {
        failWith(
          'consent_rejected',
          'checking_approval',
          'Consent check failed. Approval text was not valid.',
          { nothingCharged: true },
        )
        return
      }

      setActiveStage('simulating_payment')
      setPaymentState({ stage: 'processing', timestamp: new Date().toLocaleTimeString() })
      await new Promise((resolve) => setTimeout(resolve, 220))

      const query = selectedInsight.query_text || selectedInsight.insight_text
      const targetListingId = parseListingId(selectedInsight.listing_id)

      setActiveStage('submitting_x402')
      setConfirmationState('submitting')

      const response = await api.demoPurchase({
        user_query: query,
        buyer_address: walletInput.trim(),
        user_approval_input: 'approve',
        force_buy_for_test: false,
        target_listing_id: targetListingId,
      })

      const responseText = JSON.stringify(response).toLowerCase()
      const paymentText = JSON.stringify(response.result?.payment_status || '').toLowerCase()
      const hasInsufficientBalance =
        responseText.includes('insufficient') ||
        responseText.includes('underflow') ||
        paymentText.includes('insufficient') ||
        paymentText.includes('underflow')

      if (hasInsufficientBalance) {
        failWith(
          'insufficient_balance',
          'simulating_payment',
          'Insufficient USDC balance for this purchase. Fund wallet or choose a lower-priced insight.',
          { nothingCharged: true },
        )
        return
      }

      if (response.result?.decision === 'BUY_PENDING_APPROVAL') {
        failWith(
          'consent_rejected',
          'checking_approval',
          response.result?.message || 'Backend did not accept approval input.',
          { nothingCharged: true },
        )
        return
      }

      if (!response.success || response.result?.decision === 'SKIP' || response.result?.decision === 'ERROR') {
        failWith(
          'payment_rejected',
          'simulating_payment',
          response.message || response.result?.message || response.result?.error || 'Payment rejected by policy checks.',
          { nothingCharged: true },
        )
        return
      }

      const paymentStatus = response.result?.payment_status
      const txId =
        typeof paymentStatus === 'object' && paymentStatus?.tx_id
          ? String(paymentStatus.tx_id)
          : selectedInsight.tx_id || null

      const postPaymentOutput =
        typeof paymentStatus === 'object' && typeof paymentStatus?.post_payment_output === 'string'
          ? paymentStatus.post_payment_output
          : ''
      const paymentTxFromOutput = postPaymentOutput ? extractTxFromOutput(postPaymentOutput, 'payment') : null
      const escrowTxFromOutput = postPaymentOutput ? extractTxFromOutput(postPaymentOutput, 'escrow') : null
      const finalPaymentTx = txId || paymentTxFromOutput
      const explorerPaymentUrl =
        typeof paymentStatus === 'object' && paymentStatus?.explorer_url
          ? paymentStatus.explorer_url
          : finalPaymentTx
            ? `https://explorer.perawallet.app/tx/${finalPaymentTx}/`
            : undefined
      const explorerEscrowUrl = escrowTxFromOutput
        ? `https://explorer.perawallet.app/tx/${escrowTxFromOutput}/`
        : undefined

      setSubmittedTxId(txId)
      setActiveStage('waiting_confirmation')
      setConfirmationState('confirming')
      setPaymentState({ stage: 'confirmed', txId: txId || undefined, timestamp: new Date().toLocaleTimeString() })
      await new Promise((resolve) => setTimeout(resolve, 260))

      const outcome = deriveOutcome(response, txId)
      setActiveStage('finalizing_delivery')
      await new Promise((resolve) => setTimeout(resolve, 180))

      if (outcome.status === 'failed') {
        const failureType = outcome.detail.toLowerCase()
        if (failureType.includes('confirmation')) {
          setIssue('confirmation_failure')
        } else if (failureType.includes('escrow')) {
          setIssue('escrow_failure')
        } else {
          setIssue('delivery_failure')
        }
        setConfirmationState('failed')
        setFailedStage('finalizing_delivery')
        setStatusMessage(outcome.body)
        setDeliveryOutcome(outcome)
        setPaymentState({
          stage: 'failed',
          txId: finalPaymentTx || undefined,
          paymentTxId: finalPaymentTx || undefined,
          escrowTxId: escrowTxFromOutput || undefined,
          ipfsCid: selectedInsight.cid,
          listingId: selectedInsight.listing_id,
          deliveredInsightText: response.final_insight_text || undefined,
          escrowReleased: false,
          explorerPaymentUrl,
          explorerEscrowUrl,
          error: outcome.body,
          timestamp: new Date().toLocaleTimeString(),
        })
        return
      }

      setConfirmationState('confirmed')
      setDeliveryOutcome(outcome)
      setPaymentState({
        stage: 'completed',
        txId: finalPaymentTx || undefined,
        paymentTxId: finalPaymentTx || undefined,
        escrowTxId: escrowTxFromOutput || undefined,
        ipfsCid: selectedInsight.cid,
        listingId: selectedInsight.listing_id,
        deliveredInsightText: response.final_insight_text || undefined,
        escrowReleased: true,
        explorerPaymentUrl,
        explorerEscrowUrl,
        timestamp: new Date().toLocaleTimeString(),
      })
      if (finalPaymentTx) {
        setLastTransactionId(finalPaymentTx)
      }
      setStatusMessage('Payment approved, confirmed, and delivery finalized.')
      navigate('/transaction')
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.userMessage
          : error instanceof Error
            ? error.message
            : 'Checkout failed. Please retry.'

      const networkLike =
        message.toLowerCase().includes('timeout') ||
        message.toLowerCase().includes('network') ||
        message.toLowerCase().includes('server error')

      failWith(
        networkLike ? 'network_failure' : 'other_error',
        activeStage || 'submitting_x402',
        message,
        { nothingCharged: activeStage !== 'waiting_confirmation' && activeStage !== 'finalizing_delivery' },
      )
    } finally {
      setIsProcessing(false)
      setActiveStage(null)
    }
  }

  return (
    <div className="checkout-page">
      <section className="checkout-hero">
        <div className="home-wrap checkout-layout">
          <article className="checkout-summary-card">
            <p className="home-kicker">Final Gate</p>
            <h1>Confirm before money moves through x402.</h1>
            <p>
              This is the final approval step between evaluation and spend. Review the evaluated
              insight, confirm consent, then authorize payment.
            </p>

            <div className="checkout-purchase-grid">
              <div>
                <span>Insight</span>
                <strong>{selectedInsight.insight_text}</strong>
              </div>
              <div>
                <span>Seller</span>
                <strong>{sellerIdentity}</strong>
              </div>
              <div>
                <span>Price</span>
                <strong>{selectedInsight.price} USDC</strong>
              </div>
              <div>
                <span>Relevance rationale</span>
                <strong>{relevance ? `${relevance}% semantic fit` : rationale}</strong>
              </div>
              <div>
                <span>Reputation signal</span>
                <strong>
                  {reputation}/100 {reputation >= 70 ? 'Trusted' : reputation >= 50 ? 'Borderline' : 'Below threshold'}
                </strong>
              </div>
              <div>
                <span>Proof references</span>
                <strong>{selectedInsight.listing_id || 'No listing'} • {selectedInsight.cid || 'No CID'}</strong>
              </div>
            </div>
          </article>

          <aside className="checkout-consent-card">
            <p className="home-kicker">Explicit Consent</p>
            <h2>Approval is required before x402 execution.</h2>

            <label className="checkout-checkbox-row">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(event) => setConsentChecked(event.target.checked)}
              />
              <span>I understand this is a paid insight and I approve this transaction.</span>
            </label>

            <label className="checkout-input-group">
              <span>Type this exact sentence to confirm:</span>
              <em>{APPROVAL_TEXT}</em>
              <textarea
                value={consentText}
                onChange={(event) => setConsentText(event.target.value)}
                placeholder="Type consent sentence exactly"
              />
            </label>

            <label className="checkout-input-group">
              <span>Buyer wallet</span>
              <input
                value={walletInput}
                onChange={(event) => setWalletInput(event.target.value)}
                placeholder="Enter buyer Algorand wallet"
              />
            </label>

            <button className="checkout-btn checkout-btn--subtle" onClick={() => navigate('/trust')}>
              Read Trust / Reputation Rules
            </button>
          </aside>
        </div>
      </section>

      <section className="checkout-machine-section">
        <div className="home-wrap checkout-machine-card">
          <div className="checkout-machine-head">
            <div>
              <p className="home-kicker">Payment State Machine</p>
              <h3>Live checkout progression</h3>
            </div>
            {statusMessage && (
              <p className={`checkout-status-msg ${issue === 'insufficient_balance' ? 'is-balance' : ''}`}>
                {statusMessage}
              </p>
            )}
          </div>

          <ol className="checkout-stage-list">
            {CHECKOUT_STAGES.map((stage) => (
              <li key={stage.key} className={`is-${stageMap[stage.key]}`}>
                <div>
                  <strong>{stage.label}</strong>
                  <span>{stage.detail}</span>
                </div>
                <em>
                  {stageMap[stage.key] === 'done'
                    ? 'Done'
                    : stageMap[stage.key] === 'active'
                      ? 'In progress'
                      : stageMap[stage.key] === 'error'
                        ? 'Failed'
                        : 'Pending'}
                </em>
              </li>
            ))}
          </ol>

          {(isProcessing || submittedTxId || confirmationState !== 'idle') && (
            <div className="checkout-live-panel">
              <h4>x402 confirmation in progress</h4>
              <div className="checkout-live-grid">
                <div>
                  <span>Transaction ID</span>
                  <strong>{submittedTxId || 'Awaiting tx id from submission'}</strong>
                </div>
                <div>
                  <span>Confirmation status</span>
                  <strong>
                    {confirmationState === 'submitting'
                      ? 'Submitting to x402'
                      : confirmationState === 'confirming'
                        ? 'Waiting for confirmation'
                        : confirmationState === 'confirmed'
                          ? 'Confirmed'
                          : confirmationState === 'failed'
                            ? 'Failed'
                            : 'Idle'}
                  </strong>
                </div>
                <div>
                  <span>Estimated completion</span>
                  <strong>
                    {confirmationState === 'confirmed'
                      ? 'Completed'
                      : confirmationState === 'failed'
                        ? 'Stopped'
                        : '10-30 seconds'}
                  </strong>
                </div>
              </div>
            </div>
          )}

          {issue === 'insufficient_balance' && (
            <div className="checkout-balance-state">
              <h4>Insufficient USDC balance</h4>
              <p>
                Wallet funds are below required amount for this checkout. Fund buyer wallet or
                return to discovery and choose a lower-priced insight.
              </p>
              <div className="checkout-balance-actions">
                <button onClick={() => navigate('/discover')} className="checkout-btn checkout-btn--secondary">
                  Choose Lower-Priced Insight
                </button>
                <button onClick={() => setStatusMessage(null)} className="checkout-btn checkout-btn--ghost">
                  Retry After Funding
                </button>
              </div>
            </div>
          )}

          {deliveryOutcome && (
            <div className={`checkout-delivery-outcome ${deliveryOutcome.status === 'success' ? 'is-success' : 'is-failed'}`}>
              <h4>{deliveryOutcome.heading}</h4>
              <p>{deliveryOutcome.body}</p>
              <small>{deliveryOutcome.detail}</small>
            </div>
          )}
        </div>
      </section>

      <section className="checkout-actions">
        <div className="home-wrap checkout-actions-wrap">
          <button
            onClick={handleApprovePayment}
            disabled={isProcessing}
            className="checkout-btn checkout-btn--primary checkout-btn--dominant"
          >
            {isProcessing ? 'Processing x402 Payment...' : 'Approve and Pay'}
          </button>

          <div className="checkout-fallback-row">
            <button onClick={() => navigate('/evaluate')} className="checkout-btn checkout-btn--subtle">
              Review Insight
            </button>
            <button onClick={() => navigate('/discover')} className="checkout-btn checkout-btn--subtle">
              Edit Query
            </button>
            <button onClick={() => navigate('/evaluate')} className="checkout-btn checkout-btn--subtle">
              Go Back
            </button>
          </div>

          {deliveryOutcome?.status === 'success' && (
            <button onClick={() => navigate('/transaction')} className="checkout-btn checkout-btn--secondary">
              Open Transaction Receipt
            </button>
          )}

          <p>
            Checkout is the trust climax: you can verify what is being paid for, why it was selected,
            how x402 progresses, and what delivery outcome was reached.
            {' '}
            <a href="/trust">Open Trust / Reputation.</a>
          </p>
        </div>
      </section>
    </div>
  )
}

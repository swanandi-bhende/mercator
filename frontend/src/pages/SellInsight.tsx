import { ArrowPathIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../utils/api'
import { useAppContext } from '../context/AppContext'

type PublishStage = 'draft' | 'validating' | 'uploading' | 'listing' | 'confirming' | 'receipt'

type StudioFeedback = {
  title: string
  body: string
  nextStep: string
}

export default function SellInsightPage() {
  const navigate = useNavigate()
  const { setLastListingTxId, setListingInsight } = useAppContext()

  const [insight, setInsight] = useState('')
  const [price, setPrice] = useState('1.00')
  const [wallet, setWallet] = useState('')
  const [touched, setTouched] = useState({ insight: false, price: false, wallet: false })
  const [isLoading, setIsLoading] = useState(false)
  const [stage, setStage] = useState<PublishStage>('draft')
  const [receipt, setReceipt] = useState<{
    txId?: string
    cid?: string
    listingId?: string
    asaId?: string
    explorerUrl?: string
  } | null>(null)
  const [fieldErrors, setFieldErrors] = useState({
    insight: '',
    price: '',
    wallet: '',
  })
  const [formLockedByError, setFormLockedByError] = useState(false)
  const [studioError, setStudioError] = useState<StudioFeedback | null>(null)

  const walletPattern = useMemo(() => /^[A-Z2-7]{58}$/, [])

  const validateFields = () => {
    const nextErrors = { insight: '', price: '', wallet: '' }
    const trimmedInsight = insight.trim()
    const parsedPrice = Number(price)
    const trimmedWallet = wallet.trim().toUpperCase()

    if (!trimmedInsight) nextErrors.insight = 'Insight text is required.'
    if (!Number.isFinite(parsedPrice) || parsedPrice <= 0)
      nextErrors.price = 'Price must be greater than zero.'
    if (!trimmedWallet) {
      nextErrors.wallet = 'Wallet address is required.'
    } else if (!walletPattern.test(trimmedWallet)) {
      nextErrors.wallet = 'Wallet address must be a valid Algorand address.'
    }

    setFieldErrors(nextErrors)
    return !nextErrors.insight && !nextErrors.price && !nextErrors.wallet
  }

  const classifyError = (message: string): StudioFeedback => {
    const lowerMessage = message.toLowerCase()

    if (lowerMessage.includes('ipfs') || lowerMessage.includes('upload')) {
      return {
        title: 'Content storage failed',
        body: 'Mercator could not upload the insight to IPFS. The listing was not published.',
        nextStep: 'Check the insight text, then try publishing again when storage is available.',
      }
    }

    if (lowerMessage.includes('contract') || lowerMessage.includes('listing') || lowerMessage.includes('on-chain')) {
      return {
        title: 'Contract execution failed',
        body: 'The smart contract did not finish creating the listing record on-chain.',
        nextStep: 'Retry publication and confirm the wallet has enough balance for contract execution.',
      }
    }

    if (lowerMessage.includes('wallet') || lowerMessage.includes('address') || lowerMessage.includes('mismatch')) {
      return {
        title: 'Wallet verification failed',
        body: 'The seller wallet could not be verified or matched to the publish request.',
        nextStep: 'Confirm the Algorand address is correct and matches the wallet you want to use.',
      }
    }

    if (lowerMessage.includes('timeout') || lowerMessage.includes('confirm') || lowerMessage.includes('pending')) {
      return {
        title: 'Confirmation is delayed',
        body: 'The request reached the backend, but transaction confirmation is taking longer than expected.',
        nextStep: 'Wait briefly, then check the activity ledger for the latest confirmation status.',
      }
    }

    return {
      title: 'Publish failed',
      body: 'Mercator could not complete the listing right now.',
      nextStep: 'Review the form, then try publishing again or inspect the activity ledger for more detail.',
    }
  }

  const unlockOnEdit = () => {
    if (formLockedByError) {
      setFormLockedByError(false)
    }
  }

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setTouched({ insight: true, price: true, wallet: true })
    setStudioError(null)

    if (!validateFields()) {
      setFormLockedByError(true)
      return
    }

    setIsLoading(true)
    setFormLockedByError(false)

    try {
      setStage('validating')
      await new Promise((resolve) => setTimeout(resolve, 300))
      setStage('uploading')

      const response = await api.listInsight(insight, price, wallet.toUpperCase())

      if (!response.success || !response.txId) {
        throw new Error(response.error || 'No transaction ID returned from server.')
      }

      setStage('listing')
      await new Promise((resolve) => setTimeout(resolve, 400))
      setStage('confirming')
      await new Promise((resolve) => setTimeout(resolve, 450))
      setStage('receipt')

      // Store in context for transaction page
      setLastListingTxId(response.txId)
      setListingInsight({
        insight_text: insight,
        price: parseFloat(price as any),
        seller_wallet: wallet.toUpperCase(),
        tx_id: response.txId,
        cid: response.cid,
        listing_id: response.listing_id,
        asa_id: response.asa_id,
      })

      setReceipt({
        txId: response.txId,
        cid: response.cid,
        listingId: response.listing_id,
        asaId: response.asa_id,
        explorerUrl: response.explorer_url,
      })

      setInsight('')
      setPrice('')
      setWallet('')
      setTouched({ insight: false, price: false, wallet: false })
      setFieldErrors({ insight: '', price: '', wallet: '' })

      toast.success('Insight published. Receipt is ready.')
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.userMessage
          : error instanceof Error
            ? error.message
            : 'Could not list this insight right now. Please try again.'

      setStudioError(classifyError(message))
      setFormLockedByError(true)
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }

  const isFormDisabled = isLoading

  const stageOrder: PublishStage[] = ['draft', 'validating', 'uploading', 'listing', 'confirming', 'receipt']
  const stageIndex = stageOrder.indexOf(stage)

  return (
    <div className="sell-studio-page">
      <section className="sell-studio-hero">
        <div className="home-wrap sell-studio-layout">
          <div className="sell-studio-hero-copy">
            <p className="home-kicker">Seller Studio</p>
            <h1>Publish a market insight with proof, not just text.</h1>
            <p>
              Draft, publish, and receive a verifiable receipt as your insight moves through
              IPFS, on-chain listing, confirmation, and finalization.
            </p>
            <div className="sell-stage-pillrow" aria-label="Seller flow stages">
              <span className={stageIndex >= 0 ? 'is-active' : ''}>Draft</span>
              <span className={stageIndex >= 1 ? 'is-active' : ''}>Publish</span>
              <span className={stageIndex >= 5 || Boolean(receipt) ? 'is-active' : ''}>Receipt</span>
            </div>
            {studioError ? (
              <div className="sell-feedback-card sell-feedback-card--error">
                <p className="home-kicker">Backend feedback</p>
                <h2>{studioError.title}</h2>
                <p>{studioError.body}</p>
                <strong>Next step:</strong>
                <span>{studioError.nextStep}</span>
              </div>
            ) : (
              <div className="sell-feedback-card sell-feedback-card--success">
                <p className="home-kicker">What this page proves</p>
                <p>
                  You can validate the draft, publish to IPFS, create the on-chain listing, and
                  verify the receipt in one workspace.
                </p>
              </div>
            )}
          </div>

          <aside className="sell-studio-summary">
            <p className="home-kicker">Publishing Summary</p>
            <ul>
              <li><strong>What you do:</strong> write insight, set price, verify wallet.</li>
              <li><strong>What backend does:</strong> pin to IPFS, create listing, confirm tx.</li>
              <li><strong>What proof you get:</strong> tx ID, CID, listing ID, receipt state.</li>
            </ul>
            <button
              type="button"
              className="sell-secondary-btn"
              onClick={() => navigate('/activity')}
            >
              Open Activity Ledger
            </button>
          </aside>
        </div>
      </section>

      <section className="sell-studio-main">
        <div className="home-wrap sell-studio-grid">
          <form onSubmit={onSubmit} className="sell-studio-form">
            <div className="sell-section-card">
              <p className="home-kicker">Stage 1 · Draft</p>
              <h2>Insight Content</h2>
              <label className="sell-field">
                <span>Market insight</span>
                <textarea
                  rows={10}
                  className={fieldErrors.insight && touched.insight ? 'has-error' : ''}
                  placeholder="Example: NIFTY may retest 24500 if bank index holds support."
                  value={insight}
                  onChange={(e) => {
                    unlockOnEdit()
                    setInsight(e.target.value)
                    if (touched.insight) validateFields()
                  }}
                  onBlur={() => {
                    setTouched((current) => ({ ...current, insight: true }))
                    validateFields()
                  }}
                  disabled={isFormDisabled}
                />
                {fieldErrors.insight && touched.insight && (
                  <em>{fieldErrors.insight}</em>
                )}
              </label>
            </div>

            <div className="sell-section-card sell-section-card--twoCol">
              <div>
                <p className="home-kicker">Stage 2 · Publish</p>
                <h2>Pricing</h2>
                <label className="sell-field">
                  <span>Price in USDC</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className={fieldErrors.price && touched.price ? 'has-error' : ''}
                    value={price}
                    onChange={(e) => {
                      unlockOnEdit()
                      setPrice(e.target.value)
                      if (touched.price) validateFields()
                    }}
                    onBlur={() => {
                      setTouched((current) => ({ ...current, price: true }))
                      validateFields()
                    }}
                    placeholder="1.00"
                    disabled={isFormDisabled}
                  />
                  {fieldErrors.price && touched.price && <em>{fieldErrors.price}</em>}
                </label>
              </div>

              <div>
                <p className="home-kicker">Wallet Verification</p>
                <h2>Seller Wallet</h2>
                <label className="sell-field">
                  <span>Algorand address</span>
                  <input
                    type="text"
                    className={fieldErrors.wallet && touched.wallet ? 'has-error' : ''}
                    value={wallet}
                    onChange={(e) => {
                      unlockOnEdit()
                      setWallet(e.target.value.toUpperCase())
                      if (touched.wallet) validateFields()
                    }}
                    onBlur={() => {
                      setTouched((current) => ({ ...current, wallet: true }))
                      validateFields()
                    }}
                    placeholder="58-character Algorand wallet address"
                    disabled={isFormDisabled}
                  />
                  {fieldErrors.wallet && touched.wallet && <em>{fieldErrors.wallet}</em>}
                </label>
              </div>
            </div>

            <div className="sell-section-card">
              <p className="home-kicker">Publish Summary</p>
              <div className="sell-publish-summary">
                <div>
                  <span>Insight length</span>
                  <strong>{insight.trim().length} chars</strong>
                </div>
                <div>
                  <span>Price</span>
                  <strong>{price || '--'} USDC</strong>
                </div>
                <div>
                  <span>Wallet status</span>
                  <strong>{walletPattern.test(wallet.trim().toUpperCase()) ? 'Verified format' : 'Pending verification'}</strong>
                </div>
              </div>

              <button
                type="submit"
                disabled={isFormDisabled}
                className="sell-submit-btn"
              >
                {isLoading ? (
                  <>
                    <ArrowPathIcon className="h-4 w-4 animate-spin" />
                    {stage === 'validating' && 'Validating input...'}
                    {stage === 'uploading' && 'Uploading to IPFS...'}
                    {stage === 'listing' && 'Creating on-chain listing...'}
                    {stage === 'confirming' && 'Waiting for confirmation...'}
                    {stage === 'receipt' && 'Finalizing receipt...'}
                    {stage === 'draft' && 'Preparing publish flow...'}
                  </>
                ) : (
                  'Publish Insight'
                )}
              </button>
            </div>
          </form>

          <aside className="sell-progress-panel">
            <div className="sell-section-card">
              <p className="home-kicker">Live Publish State</p>
              <ol className="sell-progress-list">
                <li className={stageIndex >= 0 ? 'is-active' : ''}><strong>Draft</strong><span>Compose and review insight.</span></li>
                <li className={stageIndex >= 1 ? 'is-active' : ''}><strong>Validate</strong><span>Check fields and wallet format.</span></li>
                <li className={stageIndex >= 2 ? 'is-active' : ''}><strong>Upload</strong><span>Pin insight to IPFS.</span></li>
                <li className={stageIndex >= 3 ? 'is-active' : ''}><strong>List</strong><span>Create on-chain listing record.</span></li>
                <li className={stageIndex >= 4 ? 'is-active' : ''}><strong>Confirm</strong><span>Wait for chain confirmation.</span></li>
                <li className={stageIndex >= 5 ? 'is-active' : ''}><strong>Receipt</strong><span>Receive verifiable proof.</span></li>
              </ol>
            </div>

            <div className="sell-section-card sell-receipt-card">
              <p className="home-kicker">Receipt Preview</p>
              {receipt ? (
                <div>
                  <p className="sell-receipt-title">Publishing complete</p>
                  <p className="sell-receipt-summary">
                    Listing confirmed. Save this receipt for proof, then continue to activity or
                    test the buyer flow.
                  </p>
                  <div className="sell-receipt-grid">
                    <div>
                      <span>Transaction ID</span>
                      <strong>{receipt.txId}</strong>
                    </div>
                    <div>
                      <span>Listing ID</span>
                      <strong>{receipt.listingId || '--'}</strong>
                    </div>
                    <div>
                      <span>IPFS CID</span>
                      <strong>{receipt.cid || '--'}</strong>
                    </div>
                    <div>
                      <span>ASA ID</span>
                      <strong>{receipt.asaId || '--'}</strong>
                    </div>
                  </div>
                  <a href={receipt.explorerUrl || '#'} target="_blank" rel="noreferrer">
                    View explorer proof
                  </a>
                  <div className="sell-next-actions">
                    <button
                      type="button"
                      className="sell-secondary-btn"
                      onClick={() => navigate('/activity')}
                    >
                      View in Activity Ledger
                    </button>
                    <button
                      type="button"
                      className="sell-secondary-btn"
                      onClick={() => navigate('/discover')}
                    >
                      Test Buyer Discovery
                    </button>
                    <button
                      type="button"
                      className="sell-secondary-btn"
                      onClick={() => {
                        setReceipt(null)
                        setStudioError(null)
                      }}
                    >
                      Create Another Insight
                    </button>
                  </div>
                </div>
              ) : (
                <p className="sell-receipt-placeholder">
                  Once published, your tx ID, listing ID, and explorer proof will appear here.
                </p>
              )}
            </div>
          </aside>
        </div>
      </section>
    </div>
  )
}

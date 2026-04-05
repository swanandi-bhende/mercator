import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

export default function TransactionPage() {
  const navigate = useNavigate()
  const {
    lastTransactionId,
    currentJourney,
    listingInsight,
    selectedInsight,
    paymentState,
  } = useAppContext()

  if (!lastTransactionId && !paymentState?.txId) {
    return (
      <div className="min-h-screen bg-white px-4 py-12">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-bold text-gray-900">No Transaction</h1>
          <p className="mt-4 text-gray-600">
            No recent transaction found. Start a new flow to get started.
          </p>
          <button
            onClick={() => navigate('/')}
            className="mt-8 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
          >
            Back to Home
          </button>
        </div>
      </div>
    )
  }

  const txId = lastTransactionId || paymentState?.txId || ''
  const explorerUrl = `https://explorer.perawallet.app/tx/${txId}/`
  const isSellerFlow = currentJourney === 'seller'

  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        {/* Success Header */}
        <div className="mb-12 text-center">
          <div className="mb-4 text-6xl">✓</div>
          <h1 className="mb-2 text-4xl font-bold text-gray-900">
            {isSellerFlow ? 'Insight Listed Successfully' : 'Purchase Complete'}
          </h1>
          <p className="text-lg text-gray-600">
            {isSellerFlow
              ? 'Your market insight is now live on Mercator'
              : 'Your insight has been unlocked and delivered'}
          </p>
        </div>

        {/* Transaction Details Card */}
        <div className="mb-8 space-y-6">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">
              Transaction Details
            </h2>

            <div className="space-y-4">
              {/* Transaction ID */}
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Transaction ID
                </p>
                <div className="mt-1 flex items-center gap-3">
                  <code className="flex-1 break-all rounded bg-gray-100 px-3 py-2 font-mono text-sm text-gray-900">
                    {txId}
                  </code>
                  <a
                    href={explorerUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-blue-600 hover:text-blue-700 hover:underline"
                  >
                    View on Explorer
                  </a>
                </div>
              </div>

              {/* Status */}
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Status
                </p>
                <p className="mt-1 inline-block rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
                  ✓ Confirmed on Algorand
                </p>
              </div>

              {/* Details Grid */}
              <div className="grid grid-cols-2 gap-4 border-t border-gray-200 pt-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    {isSellerFlow ? 'Insight' : 'Amount'}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-gray-900">
                    {isSellerFlow
                      ? listingInsight?.insight_text?.substring(0, 40) + '...'
                      : `${selectedInsight?.price ?? '--'} USDC`}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Time
                  </p>
                  <p className="mt-1 text-sm font-semibold text-gray-900">
                    {paymentState?.timestamp ||
                      new Date().toLocaleTimeString()}
                  </p>
                </div>
                {isSellerFlow && (
                  <>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                        IPFS CID
                      </p>
                      <p className="mt-1 text-sm font-mono font-semibold text-gray-900">
                        {listingInsight?.cid?.substring(0, 12) || 'Pending...'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Listing ID
                      </p>
                      <p className="mt-1 text-sm font-mono font-semibold text-gray-900">
                        {listingInsight?.listing_id?.substring(0, 12) ||
                          'Generating...'}
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Next Steps */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h3 className="mb-3 font-bold text-blue-900">What Happens Next?</h3>
            {isSellerFlow ? (
              <ol className="space-y-2 text-sm text-blue-800">
                <li>
                  1. Your insight has been uploaded to IPFS and posted to Algorand
                </li>
                <li>
                  2. Buyers can now find and purchase your insight through the
                  discovery page
                </li>
                <li>
                  3. Your reputation score will increase with each successful sale
                </li>
                <li>4. Check Activity Ledger to see sales and confirmations</li>
              </ol>
            ) : (
              <ol className="space-y-2 text-sm text-blue-800">
                <li>1. Payment has been confirmed on-chain</li>
                <li>
                  2. Your escrow account will hold funds until you confirm receipt
                </li>
                <li>
                  3. Content is now available for download from IPFS via the CID
                </li>
                <li>4. View details and confirmations in Activity Ledger</li>
              </ol>
            )}
          </div>

          {/* Actions */}
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => navigate('/activity')}
              className="rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              View Details in Activity
            </button>
            <button
              onClick={() => navigate(isSellerFlow ? '/sell' : '/discover')}
              className="rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50"
            >
              {isSellerFlow ? 'List Another' : 'Find More'}
            </button>
          </div>

          {/* Back to Home */}
          <button
            onClick={() => navigate('/')}
            className="w-full rounded-lg border border-gray-200 px-6 py-3 text-center font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50"
          >
            ← Back to Home
          </button>
        </div>
      </div>
    </div>
  )
}

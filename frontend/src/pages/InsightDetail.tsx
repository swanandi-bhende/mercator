import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

export default function InsightDetailPage() {
  const navigate = useNavigate()
  const { selectedInsight, sellerMetadata } = useAppContext()

  if (!selectedInsight) {
    return (
      <div className="min-h-screen bg-white px-4 py-12">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-bold text-gray-900">No Insight Selected</h1>
          <p className="mt-4 text-gray-600">
            Please select an insight from the discovery page to evaluate it.
          </p>
          <button
            onClick={() => navigate('/discover')}
            className="mt-8 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
          >
            Back to Discovery
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Insight Evaluation</h1>

        <div className="space-y-6">
          {/* Insight Preview */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">The Insight</h2>
            <p className="text-gray-900">{selectedInsight.insight_text}</p>
            <p className="mt-4 text-sm text-gray-600">
              By: {selectedInsight.seller_wallet}
            </p>
          </div>

          {/* Relevance */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Relevance</h2>
            <div className="mb-2 h-2 rounded-full bg-gray-200">
              <div className="h-2 w-4/5 rounded-full bg-green-600"></div>
            </div>
            <p className="text-gray-600">80% match to your query</p>
          </div>

          {/* Seller Reputation */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Seller Reputation</h2>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-2xl font-bold text-gray-900">
                {sellerMetadata?.reputation || '—'}
              </span>
              <span className="text-sm text-gray-600">/ 100</span>
            </div>
            <p className="text-gray-600">
              {(sellerMetadata?.reputation || 0) >= 50
                ? '✓ Trusted seller'
                : '⚠ New seller'}
            </p>
          </div>

          {/* Price */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Price</h2>
            <p className="text-2xl font-bold text-gray-900">
              {selectedInsight.price} USDC
            </p>
            <p className="mt-2 text-gray-600">Fair price for market insights</p>
          </div>

          {/* Agent Decision */}
          <div className="rounded-lg border border-green-200 bg-green-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-green-900">
              Agent Recommendation
            </h2>
            <p className="text-green-800">
              ✓ This insight meets all criteria. Recommended for purchase.
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button
              onClick={() => navigate('/checkout')}
              className="flex-1 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              Continue to Checkout
            </button>
            <button
              onClick={() => navigate('/discover')}
              className="flex-1 rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50"
            >
              Decline & Search More
            </button>
          </div>

          {/* Trust Info */}
          <div className="border-t border-gray-200 pt-6">
            <p className="text-sm text-gray-600">
              Want to know more about how we evaluate insights?{' '}
              <a href="/trust" className="font-medium text-gray-900 hover:underline">
                Learn about trust and reputation
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

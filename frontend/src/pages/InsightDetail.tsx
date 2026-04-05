export default function InsightDetailPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Insight Evaluation</h1>

        <div className="space-y-6">
          {/* Relevance */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Relevance</h2>
            <p className="text-gray-600">Evaluating match to your query...</p>
          </div>

          {/* Seller Reputation */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Seller Reputation</h2>
            <p className="text-gray-600">Checking seller credibility...</p>
          </div>

          {/* Price */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Price</h2>
            <p className="text-gray-600">Evaluating pricing...</p>
          </div>

          {/* Agent Decision */}
          <div className="rounded-lg border border-green-200 bg-green-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-gray-900">Agent Recommendation</h2>
            <p className="text-gray-700">Recommending to proceed</p>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button className="flex-1 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800">
              Continue to Checkout
            </button>
            <button className="flex-1 rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50">
              Decline
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

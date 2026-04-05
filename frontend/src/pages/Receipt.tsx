export default function ReceiptPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <div className="mb-4 text-6xl">✓</div>
          <h1 className="mb-2 text-3xl font-bold text-gray-900">Purchase Complete</h1>
          <p className="text-gray-600">Your insight has been unlocked</p>
        </div>

        <div className="mt-12 space-y-6">
          {/* Transaction Details */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Transaction Details</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Transaction ID:</span>
                <span className="font-mono font-semibold text-gray-900">TX123456789</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Amount:</span>
                <span className="font-semibold text-gray-900">1.00 USDC</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Status:</span>
                <span className="font-semibold text-green-700">Confirmed</span>
              </div>
            </div>
          </div>

          {/* Insight Content */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Your Insight</h2>
            <p className="text-gray-700">This is the insight content you purchased...</p>
          </div>

          {/* Escrow Status */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-blue-900">Escrow Status</h2>
            <p className="text-blue-700">Payment held in escrow until verification</p>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button className="flex-1 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800">
              View in Activity
            </button>
            <button className="flex-1 rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50">
              Share
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

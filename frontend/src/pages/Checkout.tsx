export default function CheckoutPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Confirm Purchase</h1>

        <div className="space-y-6">
          {/* Order Summary */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Order Summary</h2>
            <div className="mb-4 flex justify-between border-b border-gray-200 pb-4">
              <span className="text-gray-600">Insight Price</span>
              <span className="font-semibold text-gray-900">1.00 USDC</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-900 font-bold">Total</span>
              <span className="font-bold text-gray-900">1.00 USDC</span>
            </div>
          </div>

          {/* Payment Method */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Payment Method</h2>
            <p className="text-gray-600">Algorand x402 Payment</p>
          </div>

          {/* Balance Check */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-blue-900">Wallet Balance</h2>
            <p className="text-blue-700">Checking balance...</p>
          </div>

          {/* Actions */}
          <button className="w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800">
            Approve Payment
          </button>
          <button className="w-full rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

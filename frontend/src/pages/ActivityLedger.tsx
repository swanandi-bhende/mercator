export default function ActivityLedgerPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Activity Ledger</h1>

        {/* Search and Filter */}
        <div className="mb-8 space-y-4">
          <input
            type="text"
            placeholder="Search by transaction ID or wallet..."
            className="w-full rounded-lg border border-gray-300 px-4 py-3 text-gray-900 outline-none focus:border-gray-500 focus:ring-2 focus:ring-gray-200"
          />
          <div className="flex gap-2">
            <button className="rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-300">
              All Transactions
            </button>
            <button className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200">
              Listings
            </button>
            <button className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200">
              Purchases
            </button>
          </div>
        </div>

        {/* Transaction List */}
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="rounded-lg border border-gray-200 p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">Transaction {i}</h3>
                <span className="text-xs font-medium text-green-700">Confirmed</span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm text-gray-600 md:grid-cols-4">
                <div>
                  <p className="text-xs font-semibold text-gray-500">TX ID</p>
                  <p className="font-mono">TX{i}23456...</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500">Amount</p>
                  <p className="font-semibold">{i}.00 USDC</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500">CID</p>
                  <p className="font-mono">QmABC...</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500">Date</p>
                  <p>2 days ago</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Export */}
        <div className="mt-8">
          <button className="rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50">
            Export Transactions
          </button>
        </div>
      </div>
    </div>
  )
}

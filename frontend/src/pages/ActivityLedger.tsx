import { useAppContext } from '../context/AppContext'

const MOCK_TRANSACTIONS = [
  {
    id: 1,
    type: 'listing',
    description: 'NIFTY insight listed',
    txId: 'TX7A3F9B2C',
    amount: '1.00 USDC',
    cid: 'QmABC123XYZ',
    status: 'confirmed',
    timestamp: '2 days ago',
  },
  {
    id: 2,
    type: 'purchase',
    description: 'Banking sector insight purchased',
    txId: 'TX4E8D5K1L',
    amount: '1.50 USDC',
    cid: 'QmDEF456ABC',
    status: 'confirmed',
    timestamp: '1 day ago',
  },
  {
    id: 3,
    type: 'listing',
    description: 'Fed speakers analysis listed',
    txId: 'TX9M2P7Q8R',
    amount: '3.00 USDC',
    cid: 'QmGHI789DEF',
    status: 'pending',
    timestamp: '5 hours ago',
  },
]

export default function ActivityLedgerPage() {
  const { lastTransactionId } = useAppContext()

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
          <div className="flex flex-wrap gap-2">
            <button className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800">
              All Transactions
            </button>
            <button className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200">
              Listings
            </button>
            <button className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200">
              Purchases
            </button>
            <div className="ml-auto">
              <button className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50">
                Export CSV
              </button>
            </div>
          </div>
        </div>

        {/* Highlight Recent Transaction */}
        {lastTransactionId && (
          <div className="mb-8 rounded-lg border-2 border-green-300 bg-green-50 p-4">
            <p className="text-sm font-semibold text-green-900">
              ✓ Recent transaction: <code className="font-mono">{lastTransactionId}</code>
            </p>
          </div>
        )}

        {/* Transaction List */}
        <div className="space-y-3">
          {MOCK_TRANSACTIONS.map((tx) => (
            <div
              key={tx.id}
              className={`rounded-lg border p-4 transition ${
                tx.id === 3
                  ? 'border-green-300 bg-green-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{tx.description}</h3>
                  <p className="text-xs text-gray-500">{tx.timestamp}</p>
                </div>
                <span
                  className={`text-xs font-medium px-2 py-1 rounded ${
                    tx.status === 'confirmed'
                      ? 'bg-green-100 text-green-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}
                >
                  {tx.status === 'confirmed' ? '✓ Confirmed' : '⏳ Pending'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm text-gray-600 md:grid-cols-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    TX ID
                  </p>
                  <a
                    href={`https://explorer.perawallet.app/tx/${tx.txId}/`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono hover:text-blue-600 hover:underline"
                  >
                    {tx.txId}
                  </a>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Amount
                  </p>
                  <p className="font-semibold text-gray-900">{tx.amount}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    IPFS CID
                  </p>
                  <a
                    href={`https://ipfs.io/ipfs/${tx.cid}`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono hover:text-blue-600 hover:underline"
                  >
                    {tx.cid.substring(0, 10)}...
                  </a>
                </div>
                <div className="hidden md:block">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Type
                  </p>
                  <p className="capitalize">{tx.type}</p>
                </div>
                <div className="hidden md:block">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Action
                  </p>
                  <button className="text-blue-600 hover:text-blue-700 hover:underline text-xs font-medium">
                    View Details
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Info */}
        <div className="mt-8 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-800">
            All transactions are recorded on Algorand TestNet and can be verified on the
            blockchain explorer. Your transaction history is immutable and auditable.
          </p>
        </div>
      </div>
    </div>
  )
}

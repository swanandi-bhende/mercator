export default function TrustPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-8 text-4xl font-bold text-gray-900">Trust & Reputation</h1>

        <div className="space-y-8">
          {/* Seller Reputation */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">Seller Reputation Score</h2>
            <p className="mb-4 text-gray-600">
              Each seller has an on-chain reputation score based on successful transactions.
            </p>
            <ul className="space-y-2 text-gray-700">
              <li>• Score 50+: Sellers can be automatically evaluated</li>
              <li>• Score &lt;50: Insights are skipped by our agent (not recommended)</li>
              <li>• New sellers start at score 0</li>
            </ul>
          </div>

          {/* How It Works */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">How It Works</h2>
            <p className="mb-4 text-gray-600">
              Our AI agent evaluates every insight based on three factors:
            </p>
            <ol className="space-y-2 text-gray-700">
              <li>1. <strong>Relevance:</strong> Does the insight match your query?</li>
              <li>2. <strong>Reputation:</strong> Is the seller trustworthy?</li>
              <li>3. <strong>Price:</strong> Is the price reasonable?</li>
            </ol>
          </div>

          {/* Low Reputation */}
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-6">
            <h2 className="mb-4 text-2xl font-bold text-yellow-900">Low Reputation Skip</h2>
            <p className="text-yellow-700">
              If a seller's reputation score is below 50, our agent will skip that insight
              automatically. This protects buyers from untrusted sellers while giving new sellers
              time to build their reputation.
            </p>
          </div>

          {/* Why It Matters */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h2 className="mb-4 text-2xl font-bold text-blue-900">Why This Matters</h2>
            <p className="mb-4 text-blue-700">
              In a peer-to-peer marketplace, reputation is everything. Mercator puts reputation
              at the center of every transaction. You can trust that:
            </p>
            <ul className="space-y-2 text-blue-700">
              <li>• All transactions are on-chain and verified</li>
              <li>• Seller reputation is transparent and auditable</li>
              <li>• Our agent enforces reputation thresholds automatically</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}

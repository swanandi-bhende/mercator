import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

const SAMPLE_INSIGHTS = [
  {
    id: '1',
    text: 'NIFTY expected to test 24500 resistance today',
    seller: 'Market Analyst Pro',
    price: 2.5,
    reputation: 87,
    relevance: 95,
  },
  {
    id: '2',
    text: 'Banking sector showing weakness, avoid financials',
    seller: 'Equity Research Lab',
    price: 1.5,
    reputation: 72,
    relevance: 78,
  },
  {
    id: '3',
    text: 'Fed speakers this week may trigger volatility',
    seller: 'Macro Observer',
    price: 3.0,
    reputation: 91,
    relevance: 65,
  },
]

export default function DiscoverInsightsPage() {
  const navigate = useNavigate()
  const { setSelectedInsight, setSellerMetadata } = useAppContext()
  const [query, setQuery] = useState('')

  const handleSelectInsight = (insight: typeof SAMPLE_INSIGHTS[0]) => {
    // Store selected insight and seller metadata in context
    setSelectedInsight({
      insight_text: insight.text,
      price: insight.price,
      seller_wallet: insight.seller,
    })

    setSellerMetadata({
      reputation: insight.reputation,
      address: insight.seller,
    })

    // Navigate to evaluation page
    navigate('/evaluate')
  }

  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-4 text-3xl font-bold text-gray-900">Find Market Insights</h1>
        <p className="mb-8 text-gray-600">
          Search for insights from verified sellers. Our AI evaluates relevance and reputation.
        </p>

        <div className="mb-12 rounded-lg border border-gray-200 bg-gray-50 p-6">
          <div className="mb-6">
            <label className="mb-2 block text-sm font-semibold text-gray-900">
              Market Question
            </label>
            <input
              type="text"
              placeholder="What is the outlook for NIFTY next week?"
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-gray-900 outline-none focus:border-gray-500 focus:ring-2 focus:ring-gray-200"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <button className="w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800">
            Search Insights
          </button>
        </div>

        {/* Results */}
        <div>
          <h2 className="mb-6 text-xl font-bold text-gray-900">Recent Insights</h2>
          <div className="space-y-4">
            {SAMPLE_INSIGHTS.map((insight) => (
              <div
                key={insight.id}
                className="rounded-lg border border-gray-200 bg-white p-6 transition hover:border-gray-300 hover:shadow-sm"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900">{insight.text}</h3>
                    <p className="mt-2 text-sm text-gray-600">by {insight.seller}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-gray-900">{insight.price} USDC</p>
                  </div>
                </div>

                {/* Stats Grid */}
                <div className="mb-4 grid grid-cols-3 gap-4 border-t border-gray-100 pt-4">
                  <div>
                    <p className="text-xs font-semibold uppercase text-gray-500">Relevance</p>
                    <p className="mt-1 text-lg font-bold text-gray-900">{insight.relevance}%</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase text-gray-500">Reputation</p>
                    <p className="mt-1 text-lg font-bold text-gray-900">{insight.reputation}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase text-gray-500">Price</p>
                    <p className="mt-1 text-sm font-semibold text-green-700">Fair ✓</p>
                  </div>
                </div>

                {/* Action */}
                <button
                  onClick={() => handleSelectInsight(insight)}
                  className="w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
                >
                  View & Evaluate
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Trust Link */}
        <div className="mt-12 rounded-lg border border-blue-200 bg-blue-50 p-6">
          <h3 className="font-bold text-blue-900">How Do We Rank These?</h3>
          <p className="mt-2 text-sm text-blue-800">
            Our AI agent evaluates relevance to your query, seller reputation score, and fair pricing.{' '}
            <a href="/trust" className="underline hover:text-blue-900">
              Learn more about trust and reputation.
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}

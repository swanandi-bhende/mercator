import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

export default function HomePage() {
  const navigate = useNavigate()
  const { setCurrentJourney } = useAppContext()

  const handleSellerMode = () => {
    setCurrentJourney('seller')
    navigate('/sell')
  }

  const handleBuyerMode = () => {
    setCurrentJourney('buyer')
    navigate('/discover')
  }

  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl text-center">
        {/* Hero */}
        <div className="mb-12">
          <h1 className="mb-4 text-5xl font-bold text-gray-900">
            Market Intelligence Marketplace
          </h1>
          <p className="text-xl text-gray-600">
            Buy and sell verified market insights on the blockchain. Transparent, trustless,
            peer-to-peer.
          </p>
        </div>

        {/* Credibility Strip */}
        <div className="mb-12 grid grid-cols-3 gap-4 rounded-lg border border-gray-200 bg-gray-50 p-8">
          <div>
            <p className="text-3xl font-bold text-gray-900">1,234</p>
            <p className="text-sm text-gray-600">Insights Listed</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-gray-900">456</p>
            <p className="text-sm text-gray-600">Verified Sellers</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-gray-900">$8.2K</p>
            <p className="text-sm text-gray-600">Total Volume</p>
          </div>
        </div>

        {/* CTAs */}
        <div className="mb-12 grid grid-cols-1 gap-8 md:grid-cols-2">
          {/* Seller CTA */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-8 transition hover:border-gray-300 hover:shadow-sm">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">📤 Share Your Insight</h2>
            <p className="mb-6 text-gray-600">
              List your market analysis and get paid when buyers purchase your insight. Your
              reputation score increases with each successful sale.
            </p>
            <button
              onClick={handleSellerMode}
              className="inline-block w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              List an Insight →
            </button>
          </div>

          {/* Buyer CTA */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-8 transition hover:border-gray-300 hover:shadow-sm">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">📥 Find Market Intelligence</h2>
            <p className="mb-6 text-gray-600">
              Search for insights from verified sellers. Our AI evaluates relevance, reputation,
              and pricing. All transactions are on-chain and auditable.
            </p>
            <button
              onClick={handleBuyerMode}
              className="inline-block w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              Find an Insight →
            </button>
          </div>
        </div>

        {/* How It Works */}
        <div className="mb-12">
          <h2 className="mb-8 text-2xl font-bold text-gray-900">How It Works</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="text-center">
              <div className="mb-3 text-4xl">📝</div>
              <p className="text-sm font-semibold text-gray-900">List</p>
              <p className="text-xs text-gray-600">Write insight</p>
            </div>
            <div className="text-center">
              <div className="mb-3 text-4xl">🔐</div>
              <p className="text-sm font-semibold text-gray-900">Upload</p>
              <p className="text-xs text-gray-600">to IPFS</p>
            </div>
            <div className="text-center">
              <div className="mb-3 text-4xl">⛓️</div>
              <p className="text-sm font-semibold text-gray-900">Post</p>
              <p className="text-xs text-gray-600">on Algorand</p>
            </div>
            <div className="text-center">
              <div className="mb-3 text-4xl">💰</div>
              <p className="text-sm font-semibold text-gray-900">Get Paid</p>
              <p className="text-xs text-gray-600">Via USDC</p>
            </div>
          </div>
        </div>

        {/* Footer Links */}
        <div className="space-y-4 border-t border-gray-200 pt-12">
          <div className="space-x-4">
            <a href="/trust" className="text-gray-600 hover:text-gray-900 hover:underline">
              How Trust Works
            </a>
            <a href="/about" className="text-gray-600 hover:text-gray-900 hover:underline">
              About Mercator
            </a>
            <a href="/operations" className="text-gray-600 hover:text-gray-900 hover:underline">
              System Status
            </a>
          </div>
          <p className="text-xs text-gray-500">
            Mercator is a blockchain-powered marketplace on Algorand TestNet
          </p>
        </div>
      </div>
    </div>
  )
}

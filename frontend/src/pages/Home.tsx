export default function HomePage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl text-center">
        <h1 className="mb-4 text-5xl font-bold text-gray-900">
          Market Intelligence Marketplace
        </h1>
        <p className="mb-12 text-xl text-gray-600">
          Buy and sell verified market insights on the blockchain
        </p>

        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          {/* Seller CTA */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-8">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">
              Share Your Insight
            </h2>
            <p className="mb-6 text-gray-600">
              List your market analysis and get paid when buyers purchase your insight.
            </p>
            <a
              href="/sell"
              className="inline-block rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              List an Insight
            </a>
          </div>

          {/* Buyer CTA */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-8">
            <h2 className="mb-4 text-2xl font-bold text-gray-900">
              Find Market Intelligence
            </h2>
            <p className="mb-6 text-gray-600">
              Search for insights from verified sellers. Our AI evaluates relevance and reputation.
            </p>
            <a
              href="/discover"
              className="inline-block rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
            >
              Find an Insight
            </a>
          </div>
        </div>

        {/* Footer Links */}
        <div className="mt-12 space-x-4">
          <a href="/trust" className="text-gray-600 underline hover:text-gray-900">
            How Trust Works
          </a>
          <a href="/about" className="text-gray-600 underline hover:text-gray-900">
            About Mercator
          </a>
          <a href="/operations" className="text-gray-600 underline hover:text-gray-900">
            System Status
          </a>
        </div>
      </div>
    </div>
  )
}

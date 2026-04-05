export default function DiscoverInsightsPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-4 text-3xl font-bold text-gray-900">Find Market Insights</h1>
        <p className="mb-8 text-gray-600">
          Search for insights from verified sellers. Our AI evaluates relevance and reputation.
        </p>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
          <div className="mb-6">
            <label className="mb-2 block text-sm font-semibold text-gray-900">
              Market Question
            </label>
            <input
              type="text"
              placeholder="What is the outlook for NIFTY next week?"
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-gray-900 outline-none focus:border-gray-500 focus:ring-2 focus:ring-gray-200"
            />
          </div>

          <button className="w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800">
            Search Insights
          </button>
        </div>

        {/* Placeholder Results */}
        <div className="mt-12">
          <h2 className="mb-4 text-xl font-bold text-gray-900">Recent Insights</h2>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-lg border border-gray-200 p-4">
                <p className="text-sm text-gray-600">Insight {i}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

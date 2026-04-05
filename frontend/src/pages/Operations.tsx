export default function OperationsPage() {
  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-2 text-3xl font-bold text-gray-900">System Status</h1>
        <p className="mb-8 text-gray-600">Backend health and operational metrics</p>

        <div className="space-y-6">
          {/* System Health */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">System Health</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-gray-600">API Server</span>
                <span className="text-sm font-medium text-green-700">✓ Operational</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Algorand Network</span>
                <span className="text-sm font-medium text-green-700">✓ Connected</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600">IPFS Gateway</span>
                <span className="text-sm font-medium text-green-700">✓ Available</span>
              </div>
            </div>
          </div>

          {/* Metrics */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Metrics</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div>
                <p className="text-xs font-semibold text-gray-500">Avg Latency</p>
                <p className="text-2xl font-bold text-gray-900">145ms</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500">Success Rate</p>
                <p className="text-2xl font-bold text-green-700">99.2%</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500">Transactions</p>
                <p className="text-2xl font-bold text-gray-900">1,234</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500">Uptime</p>
                <p className="text-2xl font-bold text-green-700">99.9%</p>
              </div>
            </div>
          </div>

          {/* Recent Events */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Recent Events</h2>
            <div className="space-y-3 text-sm">
              <div className="flex gap-3">
                <span className="text-green-700">✓</span>
                <div>
                  <p className="font-medium text-gray-900">System recovered</p>
                  <p className="text-gray-500">5 minutes ago</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="text-yellow-600">⚠</span>
                <div>
                  <p className="font-medium text-gray-900">High latency detected</p>
                  <p className="text-gray-500">12 minutes ago</p>
                </div>
              </div>
            </div>
          </div>

          {/* Operator Tools */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h2 className="mb-4 text-lg font-bold text-blue-900">Operator Tools</h2>
            <button className="w-full rounded-lg bg-blue-900 px-6 py-3 font-medium text-white hover:bg-blue-800">
              Run Test Flow
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

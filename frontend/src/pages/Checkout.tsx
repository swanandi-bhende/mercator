import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { useState } from 'react'

export default function CheckoutPage() {
  const navigate = useNavigate()
  const { selectedInsight, setPaymentState, setLastTransactionId } = useAppContext()
  const [isProcessing, setIsProcessing] = useState(false)

  if (!selectedInsight) {
    return (
      <div className="min-h-screen bg-white px-4 py-12">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-bold text-gray-900">No Insight to Checkout</h1>
          <button
            onClick={() => navigate('/discover')}
            className="mt-8 rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800"
          >
            Back to Discovery
          </button>
        </div>
      </div>
    )
  }

  const handleApprovePayment = async () => {
    setIsProcessing(true)
    
    // Simulate payment processing
    setTimeout(() => {
      // Generate mock transaction ID
      const mockTxId = `TX${Math.random().toString(16).substring(2, 10).toUpperCase()}`
      
      // Update context with payment state
      setPaymentState({
        stage: 'completed',
        txId: mockTxId,
        timestamp: new Date().toLocaleTimeString(),
      })
      
      setLastTransactionId(mockTxId)
      
      // Navigate to transaction page
      navigate('/transaction')
    }, 2000)
  }

  return (
    <div className="min-h-screen bg-white px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-3xl font-bold text-gray-900">Confirm Purchase</h1>

        <div className="space-y-6">
          {/* Order Summary */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Order Summary</h2>
            
            <div className="mb-4 rounded-lg bg-gray-50 p-4">
              <p className="text-sm font-semibold text-gray-700">
                {selectedInsight.insight_text}
              </p>
            </div>

            <div className="space-y-3 border-t border-gray-200 pt-4">
              <div className="flex justify-between">
                <span className="text-gray-600">Insight Price</span>
                <span className="font-semibold text-gray-900">
                  {selectedInsight.price} USDC
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Network Fee</span>
                <span className="font-semibold text-gray-900">0.001 ALGO</span>
              </div>
              <div className="border-t border-gray-200 pt-3 flex justify-between">
                <span className="font-bold text-gray-900">Total</span>
                <span className="font-bold text-gray-900">
                  {selectedInsight.price} USDC + tx fee
                </span>
              </div>
            </div>
          </div>

          {/* Payment Method */}
          <div className="rounded-lg border border-gray-200 p-6">
            <h2 className="mb-4 text-lg font-bold text-gray-900">Payment Method</h2>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-sm font-semibold text-gray-900">
                Algorand x402 Payment
              </p>
              <p className="text-xs text-gray-600">
                Pay with USDC on Algorand TestNet
              </p>
            </div>
          </div>

          {/* Balance Check */}
          <div className="rounded-lg border border-green-200 bg-green-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-green-900">Wallet Status</h2>
            <div className="space-y-2 text-sm text-green-800">
              <p>✓ Wallet connected</p>
              <p>✓ Sufficient balance for purchase</p>
              <p>✓ Network connection active</p>
            </div>
          </div>

          {/* Approval Notice */}
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
            <h2 className="mb-2 text-lg font-bold text-blue-900">Important</h2>
            <p className="text-sm text-blue-800">
              By clicking "Approve Payment", you authorize a payment of{' '}
              <strong>{selectedInsight.price} USDC</strong> from your connected wallet. The
              transaction will be recorded on Algorand TestNet.
            </p>
          </div>

          {/* Actions */}
          <div className="space-y-3">
            <button
              onClick={handleApprovePayment}
              disabled={isProcessing}
              className="w-full rounded-lg bg-gray-900 px-6 py-3 font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isProcessing ? 'Processing Payment...' : 'Approve Payment'}
            </button>
            <button
              onClick={() => navigate('/evaluate')}
              className="w-full rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-900 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>

          {/* Trust Footer */}
          <p className="text-center text-xs text-gray-600">
            Your payment is secured by Algorand smart contracts.{' '}
            <a href="/trust" className="font-medium text-gray-900 hover:underline">
              Learn more about security
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}

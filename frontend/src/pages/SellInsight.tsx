import { ArrowPathIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../utils/api'
import { useAppContext } from '../context/AppContext'

export default function SellInsightPage() {
  const navigate = useNavigate()
  const { setLastListingTxId, setListingInsight } = useAppContext()

  const [insight, setInsight] = useState('')
  const [price, setPrice] = useState('1.00')
  const [wallet, setWallet] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [formLockedByError, setFormLockedByError] = useState(false)

  const unlockOnEdit = () => {
    if (formLockedByError) {
      setFormLockedByError(false)
      setErrorMessage('')
    }
  }

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setErrorMessage('')

    if (!insight.trim() || !wallet.trim() || !price.trim()) {
      setErrorMessage('Please complete all fields before listing.')
      setFormLockedByError(true)
      return
    }

    setIsLoading(true)

    try {
      const response = await api.listInsight(insight, price, wallet)

      if (!response.success || !response.txId) {
        throw new Error(response.error || 'No transaction ID returned from server.')
      }

      // Store in context for transaction page
      setLastListingTxId(response.txId)
      setListingInsight({
        insight_text: insight,
        price: parseFloat(price as any),
        seller_wallet: wallet,
        tx_id: response.txId,
        cid: response.cid,
        listing_id: response.listing_id,
        asa_id: response.asa_id,
      })

      toast.success('Insight listed successfully!')
      
      // Navigate to transaction page
      navigate('/transaction')
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.userMessage
          : error instanceof Error
            ? error.message
            : 'Could not list this insight right now. Please try again.'

      setErrorMessage(message)
      setFormLockedByError(true)
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }

  const isFormDisabled = isLoading || formLockedByError

  return (
    <div className="min-h-screen bg-white px-4 py-10 md:px-6">
      <div className="mx-auto w-full max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-sm md:p-8">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Seller Console</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-900">List Insight</h1>

        <form onSubmit={onSubmit} className="mt-8 space-y-6">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-gray-700">Trading Insight</span>
            <textarea
              rows={8}
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-gray-500 focus:ring-2 focus:ring-gray-200 disabled:bg-gray-100"
              placeholder="Sample trading insight: Buy NIFTY above 24500..."
              value={insight}
              onChange={(e) => {
                unlockOnEdit()
                setInsight(e.target.value)
              }}
              disabled={isFormDisabled}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-gray-700">Price (USDC)</span>
            <input
              type="number"
              step="0.000001"
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-gray-500 focus:ring-2 focus:ring-gray-200 disabled:bg-gray-100"
              value={price}
              onChange={(e) => {
                unlockOnEdit()
                setPrice(e.target.value)
              }}
              placeholder="1.000000"
              disabled={isFormDisabled}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-gray-700">
              Seller Wallet Address
            </span>
            <input
              type="text"
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-gray-500 focus:ring-2 focus:ring-gray-200 disabled:bg-gray-100"
              value={wallet}
              onChange={(e) => {
                unlockOnEdit()
                setWallet(e.target.value)
              }}
              placeholder="Enter Algorand wallet address"
              disabled={isFormDisabled}
            />
          </label>

          <button
            type="submit"
            disabled={isFormDisabled}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-6 py-3 text-sm font-semibold text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <ArrowPathIcon className="h-4 w-4 animate-spin" />
                Uploading to IPFS & Algorand...
              </>
            ) : (
              'List Insight on Algorand'
            )}
          </button>
        </form>

        {errorMessage && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm text-red-900">{errorMessage}</p>
            <p className="mt-1 text-xs text-red-700">Edit any field to unlock and retry.</p>
          </div>
        )}
      </div>
    </div>
  )
}

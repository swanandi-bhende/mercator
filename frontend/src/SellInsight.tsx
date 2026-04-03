import { ArrowPathIcon } from '@heroicons/react/24/outline'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useState } from 'react'

export default function SellInsight() {
  const [insight, setInsight] = useState('')
  const [price, setPrice] = useState('1.00')
  const [wallet, setWallet] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [successTxId, setSuccessTxId] = useState('')
  const [demoResult, setDemoResult] = useState<string>('')
  const [errorMessage, setErrorMessage] = useState('')

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSuccessTxId('')
    setDemoResult('')
    setErrorMessage('')

    if (!insight.trim() || !wallet.trim() || !price.trim()) {
      setErrorMessage('Please complete all fields before listing.')
      return
    }

    setIsLoading(true)

    try {
      const response = await axios.post('http://localhost:8000/list', {
        insight_text: insight.trim(),
        price,
        seller_wallet: wallet.trim(),
      })

      const txId = response?.data?.txId ?? response?.data?.tx_id
      if (!txId) {
        throw new Error('No transaction ID returned from server.')
      }

      setSuccessTxId(txId)

      const demoResponse = await axios.post('http://localhost:8000/demo_purchase', {
        user_query: 'latest NIFTY insight',
        user_approval_input: 'approve',
        force_buy_for_test: true,
      })

      const finalInsightText = demoResponse?.data?.final_insight_text ?? ''
      if (typeof finalInsightText === 'string' && finalInsightText.trim()) {
        setDemoResult(finalInsightText.trim())
      }

      toast.success(
        <span>
          Insight listed successfully!{' '}
          <a
            href={`https://testnet.explorer.algorand.org/tx/${txId}`}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            View on explorer
          </a>
        </span>,
      )
    } catch (error) {
      const backendMessage =
        axios.isAxiosError(error) && typeof error.response?.data?.detail === 'string'
          ? error.response.data.detail
          : axios.isAxiosError(error) && typeof error.response?.data?.message === 'string'
            ? error.response.data.message
            : error instanceof Error
              ? error.message
              : 'Could not list this insight right now. Please try again.'

      setErrorMessage(backendMessage)
      toast.error(backendMessage)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background px-4 py-10 font-body text-ink md:px-6">
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-line bg-white p-5 shadow-sm md:p-8">
        <p className="font-headline text-xs uppercase tracking-[0.24em] text-secondary">Mercator Seller Console</p>
        <h1 className="mt-2 font-headline text-3xl font-extrabold tracking-tight">List Insight</h1>

        <form onSubmit={onSubmit} className="mt-7 space-y-5">
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Trading Insight</span>
            <textarea
              rows={8}
              className="w-full rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink outline-none ring-primary transition focus:ring-2"
              placeholder="Sample trading insight: Buy NIFTY above 24500..."
              value={insight}
              onChange={(e) => setInsight(e.target.value)}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Price (USDC)</span>
            <input
              type="number"
              step="0.000001"
              className="w-full rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink outline-none ring-primary transition focus:ring-2"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="1.000000"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Seller Wallet Address</span>
            <input
              type="text"
              className="w-full rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink outline-none ring-primary transition focus:ring-2"
              value={wallet}
              onChange={(e) => setWallet(e.target.value)}
              placeholder="Enter Algorand wallet address"
            />
          </label>

          <button
            type="submit"
            disabled={isLoading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-white transition hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-80"
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

        {demoResult && (
          <div className="mt-5 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Demo purchase result</p>
            <p className="whitespace-pre-wrap">{demoResult}</p>
          </div>
        )}

        {successTxId && (
          <div className="mt-5 rounded-lg border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-800">
            Listed successfully. Transaction:{' '}
            <a
              href={`https://testnet.explorer.algorand.org/tx/${successTxId}`}
              target="_blank"
              rel="noreferrer"
              className="font-semibold underline"
            >
              {successTxId}
            </a>
          </div>
        )}

        {errorMessage && (
          <div className="mt-5 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{errorMessage}</div>
        )}
      </div>
    </div>
  )
}

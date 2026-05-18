import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAppContext } from '../context/AppContext'
import { ApiError, api } from '../utils/api'
import type { DemoPurchaseResponse, RegisteredAgent } from '../types'

function truncateAddress(address: string) {
  if (address.length <= 14) return address
  return `${address.slice(0, 8)}...${address.slice(-4)}`
}

function explorerUrl(txId?: string) {
  return txId ? `https://lora.algokit.io/testnet/tx/${txId}` : ''
}

function formatRound(round?: number) {
  if (typeof round !== 'number' || Number.isNaN(round)) return '--'
  return round.toLocaleString()
}

function formatAgentRole(role: string) {
  return role
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ')
}

function paymentSummary(result: DemoPurchaseResponse | null) {
  const paymentStatus = result?.result?.payment_status
  if (!paymentStatus) return ''
  if (typeof paymentStatus === 'string') return paymentStatus
  return paymentStatus.message || paymentStatus.error || paymentStatus.post_payment_output || ''
}

export default function AgentsPage() {
  const { buyerWallet, setBuyerWallet } = useAppContext()
  const [agents, setAgents] = useState<RegisteredAgent[]>([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [refreshingAgents, setRefreshingAgents] = useState(false)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null)
  const [walletInput, setWalletInput] = useState(buyerWallet ?? '')
  const [queryInput, setQueryInput] = useState('Sample insight purchase for the agent marketplace')
  const [approvalInput, setApprovalInput] = useState('approve')
  const [forceBuyForTest, setForceBuyForTest] = useState(true)
  const [targetListingId, setTargetListingId] = useState('')
  const [selectedAgentWallet, setSelectedAgentWallet] = useState<string | null>(null)
  const [submittingDemo, setSubmittingDemo] = useState(false)
  const [demoResponse, setDemoResponse] = useState<DemoPurchaseResponse | null>(null)
  const [demoMessage, setDemoMessage] = useState<string | null>(null)
  const [demoError, setDemoError] = useState<string | null>(null)

  const sortedAgents = useMemo(() => {
    return [...agents].sort((left, right) => right.total_transactions - left.total_transactions)
  }, [agents])

  const loadAgents = async (showSpinner = true) => {
    if (showSpinner) setLoadingAgents(true)
    else setRefreshingAgents(true)
    setAgentsError(null)
    try {
      const response = await api.verifiedAgents()
      setAgents(response)
      setLastLoadedAt(new Date().toLocaleString())
    } catch (error) {
      const message = error instanceof ApiError ? error.userMessage : 'Unable to load registered agents'
      setAgentsError(message)
      setAgents([])
    } finally {
      setLoadingAgents(false)
      setRefreshingAgents(false)
    }
  }

  useEffect(() => {
    void loadAgents(true)
  }, [])

  useEffect(() => {
    if (buyerWallet) {
      setWalletInput(buyerWallet)
    }
  }, [buyerWallet])

  const selectAgentWallet = (wallet: string) => {
    setSelectedAgentWallet(wallet)
    setWalletInput(wallet)
    setBuyerWallet(wallet)
    toast.success('Wallet copied into the demo purchase form.')
  }

  const runSampleDemoPurchase = async () => {
    const trimmedQuery = queryInput.trim() || 'Sample insight purchase for the agent marketplace'
    const trimmedApproval = approvalInput.trim() || 'approve'
    const trimmedWallet = walletInput.trim()
    const parsedListingId = targetListingId.trim() ? Number.parseInt(targetListingId.trim(), 10) : undefined

    if (targetListingId.trim() && (!Number.isInteger(parsedListingId) || (parsedListingId ?? 0) <= 0)) {
      setDemoError('Target listing ID must be a positive number.')
      setDemoMessage(null)
      return
    }

    setSubmittingDemo(true)
    setDemoError(null)
    setDemoMessage(null)
    setDemoResponse(null)

    try {
      const response = await api.demoPurchase({
        user_query: trimmedQuery,
        buyer_address: trimmedWallet,
        user_approval_input: trimmedApproval,
        force_buy_for_test: forceBuyForTest,
        ...(typeof parsedListingId === 'number' ? { target_listing_id: parsedListingId } : {}),
      })
      setDemoResponse(response)
      setBuyerWallet(trimmedWallet || null)
      setDemoMessage(response.message || response.result?.message || 'Demo purchase completed.')
      toast.success('Demo purchase request sent.')
    } catch (error) {
      const message = error instanceof ApiError ? error.userMessage : 'Demo purchase failed'
      setDemoError(message)
      toast.error(message)
    } finally {
      setSubmittingDemo(false)
    }
  }

  const paymentStatusSummary = paymentSummary(demoResponse)
  const paymentStatus = demoResponse?.result?.payment_status && typeof demoResponse.result.payment_status === 'object'
    ? demoResponse.result.payment_status
    : null

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-amber-50 px-4 py-10 text-slate-900 md:px-6">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <div className="grid gap-8 p-6 lg:grid-cols-[1.5fr_1fr] lg:p-10">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-amber-700">Agent Marketplace</p>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950 md:text-5xl">Registered agents and a live demo purchase harness.</h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
                Browse the on-chain AgentRegistry via <span className="font-semibold text-slate-900">/agents/registered</span>, inspect each agent&apos;s role and activity, and trigger a sample buyer flow against <span className="font-semibold text-slate-900">/demo_purchase</span> from the same page.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  type="button"
                  className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
                  onClick={() => void loadAgents(false)}
                  disabled={refreshingAgents}
                >
                  {refreshingAgents ? 'Refreshing agents...' : 'Refresh registry'}
                </button>
                <button
                  type="button"
                  className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                  onClick={runSampleDemoPurchase}
                  disabled={submittingDemo}
                >
                  {submittingDemo ? 'Running demo purchase...' : 'Run sample demo purchase'}
                </button>
                <Link
                  to="/discover"
                  className="rounded-full border border-amber-200 bg-amber-50 px-5 py-3 text-sm font-semibold text-amber-900 transition hover:border-amber-300 hover:bg-amber-100"
                >
                  Explore listings
                </Link>
              </div>
            </div>

            <div className="grid gap-4 rounded-2xl bg-slate-950 p-5 text-white">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Registry Snapshot</p>
                  <p className="mt-1 text-3xl font-black">{loadingAgents ? '...' : agents.length}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-right">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Last refresh</p>
                  <p className="mt-1 text-sm font-semibold text-white">{lastLoadedAt || 'Waiting for first load'}</p>
                </div>
              </div>
              <div className="grid gap-3 text-sm text-slate-200 sm:grid-cols-2">
                <div className="rounded-2xl bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Endpoint</p>
                  <p className="mt-1 font-semibold">GET /agents/registered</p>
                </div>
                <div className="rounded-2xl bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Demo endpoint</p>
                  <p className="mt-1 font-semibold">POST /demo_purchase</p>
                </div>
              </div>
              <div className="rounded-2xl bg-amber-400/10 p-4 text-amber-50">
                <p className="text-xs uppercase tracking-[0.18em] text-amber-200">Quick use</p>
                <p className="mt-1 text-sm leading-6 text-amber-100/90">
                  Pick an agent wallet to seed the form, or leave the buyer wallet blank and let the backend use its configured test fallback.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.3fr_0.9fr]">
          <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Registered Agents</p>
                <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">AgentRegistry entries</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  Each card shows the decoded wallet, declared role, registration round, and total transactions observed on chain.
                </p>
              </div>
              <div className="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-600">
                <span className="font-semibold text-slate-900">{sortedAgents.length}</span> active agents
              </div>
            </div>

            {agentsError && (
              <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {agentsError}
              </div>
            )}

            <div className="mt-6 grid gap-4 xl:grid-cols-2">
              {loadingAgents && sortedAgents.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
                  Loading registered agents...
                </div>
              ) : sortedAgents.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
                  No registered agents were returned by the registry endpoint.
                </div>
              ) : (
                sortedAgents.map((agent, index) => (
                  <article key={`${agent.wallet}-${agent.registered_at_round}-${index}`} className={`rounded-2xl border p-5 shadow-sm transition ${selectedAgentWallet === agent.wallet ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-slate-50 hover:border-slate-300'}`}>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-bold text-slate-950">{agent.agent_name}</h3>
                          <span className="rounded-full bg-slate-950 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">{formatAgentRole(agent.role)}</span>
                        </div>
                        <p className="mt-2 font-mono text-sm text-slate-600">{truncateAddress(agent.wallet)}</p>
                      </div>
                      <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                        #{index + 1}
                      </span>
                    </div>

                    <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
                      <div className="rounded-xl bg-white p-3">
                        <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">Registered round</dt>
                        <dd className="mt-1 font-semibold text-slate-900">{formatRound(agent.registered_at_round)}</dd>
                      </div>
                      <div className="rounded-xl bg-white p-3">
                        <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">Transactions</dt>
                        <dd className="mt-1 font-semibold text-slate-900">{agent.total_transactions.toLocaleString()}</dd>
                      </div>
                    </dl>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-full bg-slate-950 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
                        onClick={() => selectAgentWallet(agent.wallet)}
                      >
                        Use for demo purchase
                      </button>
                      <span className="rounded-full border border-slate-300 px-3.5 py-2 text-xs font-semibold text-slate-600">
                        Registry verified
                      </span>
                    </div>
                  </article>
                ))
              )}
            </div>
          </article>

          <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-700">Sample Purchase</p>
              <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">Run /demo_purchase</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Use this form to exercise the buyer agent flow end to end from the marketplace page.
              </p>
            </div>

            <div className="mt-6 space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Buyer wallet</span>
                <input
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={walletInput}
                  onChange={(event) => setWalletInput(event.target.value)}
                  placeholder="Optional: wallet for the demo buyer"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">User query</span>
                <textarea
                  className="min-h-28 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder="What should the demo purchase look for?"
                />
              </label>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Approval text</span>
                  <input
                    className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                    value={approvalInput}
                    onChange={(event) => setApprovalInput(event.target.value)}
                    placeholder="approve"
                  />
                </label>

                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Target listing ID</span>
                  <input
                    className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                    value={targetListingId}
                    onChange={(event) => setTargetListingId(event.target.value)}
                    placeholder="Optional"
                    inputMode="numeric"
                  />
                </label>
              </div>

              <label className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={forceBuyForTest}
                  onChange={(event) => setForceBuyForTest(event.target.checked)}
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-slate-950 focus:ring-slate-950"
                />
                <span>
                  Force buy for test. Keep this enabled for a deterministic demo run.
                </span>
              </label>

              <button
                type="button"
                className="w-full rounded-2xl bg-amber-500 px-5 py-3.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={runSampleDemoPurchase}
                disabled={submittingDemo}
              >
                {submittingDemo ? 'Running demo purchase...' : 'Run demo purchase'}
              </button>

              {demoError && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{demoError}</div>
              )}

              {demoMessage && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{demoMessage}</div>
              )}

              {demoResponse && (
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Outcome</p>
                      <p className="mt-1 text-lg font-bold text-slate-950">{demoResponse.result?.decision || 'UNKNOWN'}</p>
                    </div>
                    {demoResponse.success ? (
                      <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">Success</span>
                    ) : (
                      <span className="rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-800">Needs review</span>
                    )}
                  </div>

                  {paymentStatusSummary && (
                    <div className="rounded-2xl bg-white p-3 text-sm text-slate-700">
                      <span className="font-semibold text-slate-900">Payment:</span> {paymentStatusSummary}
                    </div>
                  )}

                  {paymentStatus?.tx_id && (
                    <a
                      href={explorerUrl(paymentStatus.tx_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex rounded-full border border-slate-300 px-3.5 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                    >
                      View payment transaction
                    </a>
                  )}

                  {demoResponse.final_insight_text && (
                    <div className="rounded-2xl bg-white p-4">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Final insight text</p>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{demoResponse.final_insight_text}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </article>
        </section>
      </div>
    </div>
  )
}
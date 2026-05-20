import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAppContext } from '../context/AppContext'
import { ApiError, api } from '../utils/api'

export default function LoginPage() {
  const navigate = useNavigate()
  const { setBuyerWallet } = useAppContext()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ user_id: string; algo_address: string; session_token: string } | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const response = await api.login({ email: email.trim(), password })
      const session = {
        user_id: response.user_id,
        algo_address: response.algo_address,
        display_name: email.trim() || 'Mercator User',
        session_token: response.session_token,
      }
      localStorage.setItem('mercator_session', JSON.stringify(session))
      setBuyerWallet(response.algo_address)
      setResult(response)
      toast.success('Logged in successfully.')
    } catch (err) {
      const message = err instanceof ApiError ? err.userMessage : 'Login failed'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mercator-themed-page min-h-screen bg-[radial-gradient(1000px_520px_at_0%_0%,rgba(220,176,153,0.22),transparent_58%),radial-gradient(860px_460px_at_100%_0%,rgba(111,57,70,0.14),transparent_54%),linear-gradient(180deg,#fff8f4_0%,#fffdf8_100%)] px-4 py-10 text-slate-900 md:px-6">
      <div className="mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6 md:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">Sign In</p>
          <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950">Return to your buyer session.</h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-slate-600">
            Use your email and password to resume a custodial wallet session, continue buying insights, and keep your buyer wallet in sync across the app.
          </p>

          <form className="mt-8 grid gap-4" onSubmit={handleSubmit}>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Email</span>
              <input
                type="email"
                className="rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
              />
            </label>

            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Password</span>
              <input
                type="password"
                className="rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your Mercator password"
                required
              />
            </label>

            {error && <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

            <button
              type="submit"
              className="rounded-2xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={loading}
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          {result && (
            <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              <p className="font-semibold">Logged in successfully.</p>
              <p className="mt-1 break-all">Wallet: {result.algo_address}</p>
              <p className="mt-1 break-all">Session token: {result.session_token}</p>
              <button
                type="button"
                className="mt-4 rounded-full bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
                onClick={() => navigate('/discover')}
              >
                Continue to discovery
              </button>
            </div>
          )}
        </section>

        <aside className="grid gap-4">
          <section className="mercator-elevated-card rounded-3xl border border-slate-200 bg-slate-950 p-6 text-white">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">New here?</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight">Create a custodial wallet first.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              The onboarding flow at /onboard sets up a wallet, funds TestNet USDC, and stores your session automatically.
            </p>
            <Link
              to="/onboard"
              className="mt-5 inline-flex rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
            >
              Go to onboarding
            </Link>
          </section>

          <section className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Wallet Tools</p>
            <h3 className="mt-2 text-xl font-black text-slate-950">Export, import, or verify custody.</h3>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              If you already have a wallet, use the wallet center to check whether it is custodial and export the mnemonic for migration.
            </p>
            <Link
              to="/wallet-tools"
              className="mt-5 inline-flex rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
            >
              Open wallet tools
            </Link>
          </section>

          <section className="mercator-elevated-card rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">Backend path</p>
            <p className="mt-2 text-sm leading-6">
              This form calls the server&apos;s <span className="font-semibold">POST /auth/login</span> endpoint directly.
            </p>
          </section>
        </aside>
      </div>
    </div>
  )
}
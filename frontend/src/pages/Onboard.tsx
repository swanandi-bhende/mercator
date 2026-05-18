import { FormEvent, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../utils/api'

type OnboardStep = 'form' | 'funding' | 'ready'

type OnboardResult = {
  user_id: string
  session_token: string
  algo_address: string
  display_name: string
  algo_balance_micro: number
  usdc_balance_micro: number
  funding_status: string
  message: string
}

function truncatedAddress(address: string) {
  if (!address) return ''
  if (address.length <= 12) return address
  return `${address.slice(0, 8)}...${address.slice(-4)}`
}

export default function OnboardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<OnboardStep>('form')
  const [statusText, setStatusText] = useState('Setting up your wallet...')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<OnboardResult | null>(null)

  const passwordStrength = useMemo(() => {
    if (password.length < 10) {
      return { label: 'Weak', className: 'onboard-strength onboard-strength--weak' }
    }
    if (!/\d/.test(password)) {
      return { label: 'Fair', className: 'onboard-strength onboard-strength--fair' }
    }
    return { label: 'Good', className: 'onboard-strength onboard-strength--good' }
  }, [password])

  const runFundingAnimation = () => {
    setStep('funding')
    setStatusText('Setting up your wallet...')
    window.setTimeout(() => setStatusText('Funding with TestNet USDC...'), 2000)
    window.setTimeout(() => setStatusText('Almost ready...'), 4000)
    window.setTimeout(() => setStep('ready'), 5000)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const onboard = await api.onboard({
        display_name: displayName.trim(),
        email: email.trim(),
        password,
      })
      const payload = {
        user_id: onboard.user_id,
        algo_address: onboard.algo_address,
        display_name: onboard.display_name,
        session_token: onboard.session_token,
      }
      localStorage.setItem('mercator_session', JSON.stringify(payload))
      setResult(onboard)
      runFundingAnimation()
    } catch (err) {
      const apiError = err as ApiError
      setError(apiError.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (step === 'funding') {
    return (
      <div className="onboard-fullscreen">
        <div className="onboard-pulse-wrap">
          <div className="onboard-pulse-ring" />
          <div className="onboard-pulse-core">A</div>
        </div>
        <h1 className="onboard-funding-title">{statusText}</h1>
      </div>
    )
  }

  if (step === 'ready' && result) {
    return (
      <div className="onboard-page">
        <section className="onboard-card onboard-card--ready">
          <p className="onboard-kicker">Wallet Ready</p>
          <h1>Welcome, {result.display_name}</h1>
          <p className="onboard-address">{truncatedAddress(result.algo_address)}</p>
          <p className="onboard-usdc">${(result.usdc_balance_micro / 1_000_000).toFixed(2)} USDC</p>
          <p className="onboard-algo">{(result.algo_balance_micro / 1_000_000).toFixed(3)} ALGO</p>
          <button className="onboard-primary-btn" onClick={() => navigate('/discover')}>
            Explore Insights →
          </button>
        </section>
      </div>
    )
  }

  return (
    <div className="onboard-page">
      <section className="onboard-card">
        <p className="onboard-kicker">Start Free</p>
        <h1>Create your Mercator wallet</h1>
        <div className="mt-3 flex flex-wrap gap-3 text-sm">
          <Link to="/login" className="font-semibold text-[#7d474f] underline underline-offset-4">
            Already onboarded? Sign in.
          </Link>
          <Link to="/wallet" className="font-semibold text-[#1f707f] underline underline-offset-4">
            Need wallet export/import tools?
          </Link>
        </div>
        <form onSubmit={handleSubmit} className="onboard-form">
          <label>
            Display name
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              minLength={2}
              maxLength={50}
              required
            />
          </label>
          <label>
            Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              required
            />
          </label>
          <label>
            Password
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              required
            />
          </label>
          <p className={passwordStrength.className}>Password strength: {passwordStrength.label}</p>
          {error && <p className="onboard-error">{error}</p>}
          <button type="submit" disabled={submitting} className="onboard-primary-btn">
            {submitting ? 'Creating wallet...' : 'Get Started'}
          </button>
        </form>
      </section>
    </div>
  )
}

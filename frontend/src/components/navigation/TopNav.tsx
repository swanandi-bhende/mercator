import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAppContext } from '../../context/AppContext'
import { useEffect, useState } from 'react'
import { api } from '../../utils/api'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

function connectionLabel(status: ConnectionStatus) {
  if (status === 'connected') return 'Live'
  if (status === 'connecting') return 'Connecting...'
  return 'Offline'
}

export default function TopNav({ connectionStatus }: { connectionStatus: ConnectionStatus }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { currentJourney, setCurrentJourney } = useAppContext()
  const [menuOpen, setMenuOpen] = useState(false)
  const [walletMenuOpen, setWalletMenuOpen] = useState(false)
  const [session, setSession] = useState<{ user_id: string; algo_address: string; display_name: string; session_token?: string } | null>(null)
  const [balances, setBalances] = useState<{ usdc: number; algo: number }>({ usdc: 0, algo: 0 })

  const isActive = (path: string) => location.pathname === path

  const truncateAddress = (address: string) => {
    if (address.length <= 12) return address
    return `${address.slice(0, 8)}...${address.slice(-4)}`
  }

  const loadSession = () => {
    const raw = localStorage.getItem('mercator_session')
    if (!raw) {
      setSession(null)
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (parsed?.user_id && parsed?.algo_address) {
        setSession(parsed)
        return
      }
      setSession(null)
    } catch {
      setSession(null)
    }
  }

  // Update journey based on current route
  useEffect(() => {
    if (location.pathname.includes('/sell')) {
      setCurrentJourney('seller')
    } else if (['/discover', '/evaluate', '/checkout', '/transaction', '/receipt', '/subscription', '/agents', '/agents/registered'].includes(location.pathname)) {
      setCurrentJourney('buyer')
    } else if (location.pathname === '/') {
      setCurrentJourney('home')
    }
  }, [location.pathname, setCurrentJourney])

  useEffect(() => {
    loadSession()
  }, [location.pathname])

  useEffect(() => {
    if (!session?.algo_address) {
      return
    }

    let mounted = true
    const refreshBalance = async () => {
      try {
        const response = await api.walletBalance(session.algo_address)
        if (!mounted) return
        setBalances({
          usdc: response.usdc_balance_micro / 1_000_000,
          algo: response.algo_balance_micro / 1_000_000,
        })
      } catch {
        // Keep stale balance if refresh fails.
      }
    }

    refreshBalance()
    const id = window.setInterval(refreshBalance, 30000)
    return () => {
      mounted = false
      window.clearInterval(id)
    }
  }, [session?.algo_address])

  const switchFlow = (journey: 'seller' | 'buyer' | 'home') => {
    setCurrentJourney(journey)
    setMenuOpen(false)
    switch (journey) {
      case 'seller':
        navigate('/sell')
        break
      case 'buyer':
        navigate('/discover')
        break
      case 'home':
        navigate('/')
        break
    }
  }

  const journeyLabel = {
    home: '🏠 Home',
    seller: '📤 Seller Mode',
    buyer: '📥 Buyer Mode',
  }

  const indicatorClass =
    connectionStatus === 'connected'
      ? 'ws-dot ws-dot--connected'
      : connectionStatus === 'connecting'
        ? 'ws-dot ws-dot--connecting'
        : 'ws-dot ws-dot--disconnected'

  return (
    <nav className="mercator-topnav sticky top-0 z-50 border-b border-gray-200 bg-white bg-opacity-95 backdrop-blur">
      <div className="mercator-topnav__inner mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mercator-topnav__row flex h-16 items-center justify-between">
          {/* Brand + Journey Indicator */}
          <div className="mercator-topnav__brand-group flex items-center gap-6">
            <Link to="/" className="mercator-topnav__brand flex items-center gap-2">
              <span className="text-xl font-bold text-gray-900">mercator</span>
            </Link>

            {/* Journey Badge */}
            <div className="mercator-topnav__journey hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-gray-100">
              <span className="text-xs font-semibold text-gray-600">
                {journeyLabel[currentJourney]}
              </span>
            </div>

            {/* Core Navigation */}
            <div className="mercator-topnav__links hidden gap-6 lg:flex">
              <NavLink
                href="/sell"
                active={isActive('/sell')}
                label="List Insight"
              />
              <NavLink
                href="/discover"
                active={isActive('/discover')}
                label="Find Insight"
              />
              <NavLink
                href="/subscription"
                active={isActive('/subscription')}
                label="Subscription"
              />
              <NavLink
                href="/agents"
                active={isActive('/agents') || isActive('/agents/registered')}
                label="Agents"
              />
              <NavLink
                href="/activity"
                active={isActive('/activity')}
                label="Activity"
              />
              <NavLink
                href="/trust"
                active={isActive('/trust')}
                label="Trust"
              />
            </div>
          </div>

          {/* Right Actions */}
          <div className="mercator-topnav__actions flex items-center gap-3">
            <div className="ws-status-indicator mercator-topnav__status" aria-live="polite">
              <span className={indicatorClass} />
              <span className="ws-status-text">{connectionLabel(connectionStatus)}</span>
            </div>

            {session ? (
              <>
                <div className="wallet-panel">
                  <div className="wallet-panel-main">
                    <p className="wallet-panel-name">{session.display_name || 'Mercator User'}</p>
                    <p className="wallet-panel-address">{truncateAddress(session.algo_address)}</p>
                  </div>
                  <div className="wallet-panel-balance">
                    <p className="wallet-panel-usdc">${balances.usdc.toFixed(2)} USDC</p>
                    <p className="wallet-panel-algo">{balances.algo.toFixed(3)} ALGO</p>
                  </div>
                </div>
                <div className="wallet-actions mercator-topnav__wallet-actions">
                  <button onClick={() => setWalletMenuOpen((prev) => !prev)}>⋯</button>
                  {walletMenuOpen && (
                    <div className="wallet-dropdown">
                      <button
                        onClick={() => {
                          localStorage.removeItem('mercator_session')
                          setSession(null)
                          setWalletMenuOpen(false)
                          navigate('/')
                        }}
                      >
                        Sign Out
                      </button>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex items-center gap-2">
                <button className="home-btn home-btn--secondary" onClick={() => navigate('/login')}>
                  Sign In
                </button>
                <button className="home-btn home-btn--primary" onClick={() => navigate('/onboard')}>
                  Sign Up Free
                </button>
                <button className="home-btn home-btn--secondary hidden sm:inline-flex" onClick={() => navigate('/wallet-tools')}>
                  Wallet
                </button>
              </div>
            )}

            {/* Flow Switcher - Visible on all sizes */}
            <div className="mercator-topnav__flow-switcher hidden md:flex items-center gap-1 border-l border-gray-200 pl-3">
              <button
                onClick={() => switchFlow('seller')}
                className={`mercator-topnav__flow-btn text-xs font-medium px-2 py-1 rounded transition-colors ${
                  currentJourney === 'seller'
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Sell
              </button>
              <button
                onClick={() => switchFlow('buyer')}
                className={`mercator-topnav__flow-btn text-xs font-medium px-2 py-1 rounded transition-colors ${
                  currentJourney === 'buyer'
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Buy
              </button>
            </div>

            {/* Admin Link */}
            <Link
              to="/operations"
              className="mercator-topnav__ops hidden text-xs font-medium text-gray-500 hover:text-gray-900 md:inline"
            >
              Operations
            </Link>

            {/* Mobile Menu Toggle */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="mercator-topnav__menu-toggle md:hidden text-gray-900 p-2"
            >
              ☰
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {menuOpen && (
          <div className="mercator-topnav__mobile-menu border-t border-gray-200 bg-white py-3 px-4 md:hidden">
            <div className="space-y-2">
              <Link
                to="/sell"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                List Insight
              </Link>
              <Link
                to="/login"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Sign In
              </Link>
              <Link
                to="/discover"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Find Insight
              </Link>
              <Link
                to="/wallet-tools"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Wallet Tools
              </Link>
              <Link
                to="/subscription"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Subscription
              </Link>
              <Link
                to="/agents"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Agents
              </Link>
              <Link
                to="/activity"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Activity
              </Link>
              <Link
                to="/trust"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Trust & Reputation
              </Link>
              <Link
                to="/operations"
                className="mercator-topnav__mobile-link block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Operations
              </Link>
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}

function NavLink({
  href,
  label,
  active,
}: {
  href: string
  label: string
  active: boolean
}) {
  return (
    <Link
      to={href}
      className={`mercator-topnav__link text-sm font-medium transition-colors ${
        active
          ? 'border-b-2 border-gray-900 text-gray-900'
          : 'border-b-2 border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
    </Link>
  )
}

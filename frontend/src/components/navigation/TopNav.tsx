import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAppContext } from '../../context/AppContext'
import { useEffect, useState } from 'react'

export default function TopNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const { currentJourney, setCurrentJourney } = useAppContext()
  const [menuOpen, setMenuOpen] = useState(false)

  const isActive = (path: string) => location.pathname === path

  // Update journey based on current route
  useEffect(() => {
    if (location.pathname.includes('/sell')) {
      setCurrentJourney('seller')
    } else if (['/discover', '/evaluate', '/checkout', '/transaction'].includes(location.pathname)) {
      setCurrentJourney('buyer')
    } else if (location.pathname === '/') {
      setCurrentJourney('home')
    }
  }, [location.pathname, setCurrentJourney])

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

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-200 bg-white bg-opacity-95 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Brand + Journey Indicator */}
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2">
              <span className="text-xl font-bold text-gray-900">mercator</span>
            </Link>

            {/* Journey Badge */}
            <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-gray-100">
              <span className="text-xs font-semibold text-gray-600">
                {journeyLabel[currentJourney]}
              </span>
            </div>

            {/* Core Navigation */}
            <div className="hidden gap-6 lg:flex">
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
          <div className="flex items-center gap-3">
            {/* Flow Switcher - Visible on all sizes */}
            <div className="hidden md:flex items-center gap-1 border-l border-gray-200 pl-3">
              <button
                onClick={() => switchFlow('seller')}
                className={`text-xs font-medium px-2 py-1 rounded transition-colors ${
                  currentJourney === 'seller'
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Sell
              </button>
              <button
                onClick={() => switchFlow('buyer')}
                className={`text-xs font-medium px-2 py-1 rounded transition-colors ${
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
              className="hidden text-xs font-medium text-gray-500 hover:text-gray-900 md:inline"
            >
              Ops
            </Link>

            {/* Mobile Menu Toggle */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden text-gray-900 p-2"
            >
              ☰
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {menuOpen && (
          <div className="border-t border-gray-200 bg-white py-3 px-4 md:hidden">
            <div className="space-y-2">
              <Link
                to="/sell"
                className="block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                List Insight
              </Link>
              <Link
                to="/discover"
                className="block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Find Insight
              </Link>
              <Link
                to="/activity"
                className="block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Activity
              </Link>
              <Link
                to="/trust"
                className="block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                Trust & Reputation
              </Link>
              <Link
                to="/operations"
                className="block px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 rounded"
                onClick={() => setMenuOpen(false)}
              >
                System Status
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
      className={`text-sm font-medium transition-colors ${
        active
          ? 'border-b-2 border-gray-900 text-gray-900'
          : 'border-b-2 border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
    </Link>
  )
}

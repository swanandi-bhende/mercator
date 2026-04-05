import { Link, useLocation } from 'react-router-dom'

export default function TopNav() {
  const location = useLocation()

  const isActive = (path: string) => location.pathname === path

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-200 bg-white bg-opacity-95 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Brand */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2">
              <span className="text-xl font-bold text-gray-900">mercator</span>
            </Link>

            {/* Core Navigation */}
            <div className="hidden gap-6 md:flex">
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
            </div>
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-4">
            <Link
              to="/trust"
              className="hidden text-sm text-gray-600 hover:text-gray-900 md:inline"
            >
              Trust & Reputation
            </Link>
            <Link
              to="/"
              className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
            >
              Home
            </Link>
          </div>
        </div>
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

import { Link, Outlet } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import TopNav from '../components/navigation/TopNav'

export default function MainLayout() {
  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-center" />
      <TopNav />
      <main className="transition-opacity duration-300">
        <Outlet />
      </main>
      <footer className="border-t border-gray-200 bg-white/90">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 text-sm text-gray-600 sm:px-6 lg:px-8">
          <p>Mercator auditability is always available.</p>
          <div className="flex flex-wrap items-center gap-4">
            <Link to="/activity" className="font-semibold text-gray-800 hover:text-gray-900">
              Open Activity Ledger
            </Link>
            <Link to="/trust" className="hover:text-gray-900">
              Trust Rules
            </Link>
            <Link to="/about" className="hover:text-gray-900">
              About
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

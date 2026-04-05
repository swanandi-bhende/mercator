import { Outlet } from 'react-router-dom'
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
    </div>
  )
}

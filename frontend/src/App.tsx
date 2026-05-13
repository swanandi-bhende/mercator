import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppProvider } from './context/AppContext'
import Layout from './components/Layout'
import HomePage from './pages/Home'
import SellInsightPage from './pages/SellInsight'
import DiscoverInsightsPage from './pages/DiscoverInsights'
import InsightDetailPage from './pages/InsightDetail'
import SellerProfilePage from './pages/SellerProfile'
import CheckoutPage from './pages/Checkout'
import TransactionPage from './pages/Transaction'
import TrustPage from './pages/Trust'
import ActivityLedgerPage from './pages/ActivityLedger'
import OperationsPage from './pages/Operations'
import AboutPage from './pages/About'
import OnboardPage from './pages/Onboard'

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route element={<Layout />}>
            {/* Public Landing Route */}
            <Route path="/" element={<HomePage />} />

            {/* Seller Journey Route Group */}
            <Route path="/sell" element={<SellInsightPage />} />

            {/* Buyer Journey Route Group */}
            <Route path="/discover" element={<DiscoverInsightsPage />} />
            <Route path="/evaluate" element={<InsightDetailPage />} />
            <Route path="/sellers/:wallet" element={<SellerProfilePage />} />
            <Route path="/checkout" element={<CheckoutPage />} />

            {/* Shared Transaction Route (seller listing success, buyer purchase success) */}
            <Route path="/transaction" element={<TransactionPage />} />

            {/* Shared Routes */}
            <Route path="/onboard" element={<OnboardPage />} />
            <Route path="/trust" element={<TrustPage />} />
            <Route path="/activity" element={<ActivityLedgerPage />} />

            {/* Operations & Admin Route */}
            <Route path="/operations" element={<OperationsPage />} />

            {/* Information Route */}
            <Route path="/about" element={<AboutPage />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  )
}

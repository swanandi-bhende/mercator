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
import SubscriptionManagerPage from './pages/SubscriptionManager'
import TrustPage from './pages/Trust'
import ActivityLedgerPage from './pages/ActivityLedger'
import OperationsPage from './pages/Operations'
import AgentsPage from './pages/Agents'
import LoginPage from './pages/Login'
import WalletToolsPage from './pages/WalletTools'
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
            <Route path="/subscription" element={<SubscriptionManagerPage />} />

            {/* Shared Transaction Route (seller listing success, buyer purchase success) */}
            <Route path="/transaction" element={<TransactionPage />} />
            <Route path="/receipt" element={<TransactionPage />} />

            {/* Shared Routes */}
            <Route path="/onboard" element={<OnboardPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/auth/login" element={<LoginPage />} />
            <Route path="/wallet" element={<WalletToolsPage />} />
            <Route path="/trust" element={<TrustPage />} />
            <Route path="/activity" element={<ActivityLedgerPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/agents/registered" element={<AgentsPage />} />

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

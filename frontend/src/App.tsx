import { BrowserRouter, Routes, Route } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import HomePage from './pages/Home'
import SellInsightPage from './pages/SellInsight'
import DiscoverInsightsPage from './pages/DiscoverInsights'
import InsightDetailPage from './pages/InsightDetail'
import CheckoutPage from './pages/Checkout'
import ReceiptPage from './pages/Receipt'
import TrustPage from './pages/Trust'
import ActivityLedgerPage from './pages/ActivityLedger'
import OperationsPage from './pages/Operations'
import AboutPage from './pages/About'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          {/* Public Landing Route */}
          <Route path="/" element={<HomePage />} />

          {/* Seller Journey Route Group */}
          <Route path="/sell" element={<SellInsightPage />} />

          {/* Buyer Journey Route Group */}
          <Route path="/discover" element={<DiscoverInsightsPage />} />
          <Route path="/evaluate" element={<InsightDetailPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/receipt" element={<ReceiptPage />} />

          {/* Shared Routes */}
          <Route path="/trust" element={<TrustPage />} />
          <Route path="/activity" element={<ActivityLedgerPage />} />

          {/* Operations & Admin Route */}
          <Route path="/operations" element={<OperationsPage />} />

          {/* Information Route */}
          <Route path="/about" element={<AboutPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

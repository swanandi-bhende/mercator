import { Link, Outlet } from "react-router-dom"
import { Toaster } from "react-hot-toast"
import { useCallback, useEffect, useState } from "react"
import TopNav from "./navigation/TopNav"
import useConnectionStatus, { ConnectionStatus } from "../hooks/useConnectionStatus"
import type { WebSocketEvent } from "../hooks/useWebSocket"

export type LayoutOutletContext = {
  latestWsEvent: WebSocketEvent | null
}

interface SystemAlert {
  alertId: string
  severity: string
  message: string
  affectedComponents: string[]
  timestamp: string
}

export default function Layout() {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const [latestWsEvent, setLatestWsEvent] = useState<WebSocketEvent | null>(null)
  const [systemAlert, setSystemAlert] = useState<SystemAlert | null>(null)

  const onMessage = useCallback((event: WebSocketEvent) => {
    setLatestWsEvent(event)
    // Handle system_alert events for the banner
    if (event.type === "system_alert" && event.data) {
      setSystemAlert({
        alertId: event.data.alert_id || event.data.alertId || "",
        severity: event.data.severity || "critical",
        message: event.data.message || "System component failure detected",
        affectedComponents: event.data.affected_components || event.data.affectedComponents || [],
        timestamp: event.data.timestamp || new Date().toISOString(),
      })
    }
  }, [])

  const statusState = useConnectionStatus(onMessage)

  useEffect(() => {
    setConnectionStatus(statusState.connectionStatus)
  }, [statusState.connectionStatus])

  const dismissAlert = () => {
    setSystemAlert(null)
  }

  return (
    <div className="mercator-shell">
      <Toaster position="top-center" />
      {systemAlert && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-50 border-b border-red-200 p-4">
          <div className="mx-auto max-w-7xl flex items-start justify-between px-4 sm:px-6 lg:px-8">
            <div className="flex-1">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-red-800">⚠️ System Alert</h3>
                  <p className="mt-1 text-sm text-red-700">{systemAlert.message}</p>
                  {systemAlert.affectedComponents.length > 0 && (
                    <p className="mt-1 text-xs text-red-600">
                      Affected: {systemAlert.affectedComponents.join(", ")}
                    </p>
                  )}
                </div>
              </div>
            </div>
            <button
              onClick={dismissAlert}
              className="flex-shrink-0 text-red-400 hover:text-red-600 ml-3"
              aria-label="Dismiss alert"
            >
              <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      )}
      <TopNav connectionStatus={connectionStatus} />
      <main className={`transition-opacity duration-300 ${systemAlert ? "pt-24" : ""}`}>
        <Outlet context={{ latestWsEvent } satisfies LayoutOutletContext} />
      </main>
      <footer className="home-footer mercator-footer">
        <div className="home-wrap home-footer-grid mercator-footer__grid">
          <div>
            <p className="home-kicker">Auditability</p>
            <h3>Mercator keeps proof visible across every route.</h3>
            <p>
              Discover, subscribe, buy, and review activity from the same visual system used on the landing page.
            </p>
          </div>
          <div className="home-footer-links mercator-footer__links">
            <Link to="/activity" className="mercator-footer__link">
              Open Activity Ledger
            </Link>
            <Link to="/operations" className="mercator-footer__link">
              Open Operations Dashboard
            </Link>
            <Link to="/subscription" className="mercator-footer__link">
              Subscription Manager
            </Link>
            <Link to="/agents" className="mercator-footer__link">
              Registered Agents
            </Link>
            <Link to="/trust" className="mercator-footer__link">
              Trust Rules
            </Link>
            <Link to="/about" className="mercator-footer__link">
              About
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

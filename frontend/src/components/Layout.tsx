import { Link, Outlet } from "react-router-dom"
import { Toaster } from "react-hot-toast"
import { useCallback, useEffect, useState } from "react"
import TopNav from "./navigation/TopNav"
import useConnectionStatus, { ConnectionStatus } from "../hooks/useConnectionStatus"
import type { WebSocketEvent } from "../hooks/useWebSocket"

export type LayoutOutletContext = {
  latestWsEvent: WebSocketEvent | null
}

export default function Layout() {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const [latestWsEvent, setLatestWsEvent] = useState<WebSocketEvent | null>(null)

  const onMessage = useCallback((event: WebSocketEvent) => {
    setLatestWsEvent(event)
  }, [])

  const statusState = useConnectionStatus(onMessage)

  useEffect(() => {
    setConnectionStatus(statusState.connectionStatus)
  }, [statusState.connectionStatus])

  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-center" />
      <TopNav connectionStatus={connectionStatus} />
      <main className="transition-opacity duration-300">
        <Outlet context={{ latestWsEvent } satisfies LayoutOutletContext} />
      </main>
      <footer className="border-t border-gray-200 bg-white/90">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 text-sm text-gray-600 sm:px-6 lg:px-8">
          <p>Mercator auditability is always available.</p>
          <div className="flex flex-wrap items-center gap-4">
            <Link to="/activity" className="font-semibold text-gray-800 hover:text-gray-900">
              Open Activity Ledger
            </Link>
            <Link to="/operations" className="font-semibold text-gray-800 hover:text-gray-900">
              Open Operations Dashboard
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

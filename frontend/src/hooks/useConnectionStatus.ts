import { useRef, useState } from "react"
import toast from "react-hot-toast"
import useWebSocket, { WebSocketEvent } from "./useWebSocket"

export type ConnectionStatus = "connecting" | "connected" | "disconnected"

export default function useConnectionStatus(onMessage: (event: WebSocketEvent) => void) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const sawDisconnectRef = useRef(false)

  useWebSocket(onMessage, {
    onOpen: () => {
      setConnectionStatus("connected")
      if (sawDisconnectRef.current) {
        toast.success("Reconnected", { duration: 1800 })
        sawDisconnectRef.current = false
      }
    },
    onClose: () => {
      sawDisconnectRef.current = true
      setConnectionStatus("disconnected")
    },
    onError: () => {
      setConnectionStatus("disconnected")
    },
  })

  return { connectionStatus }
}

import { useEffect, useRef } from "react"

export interface WebSocketEvent {
  event_type: string
  timestamp: string
  payload: Record<string, unknown>
}

type UseWebSocketOptions = {
  onOpen?: () => void
  onClose?: (event: CloseEvent) => void
  onError?: (error: Event) => void
}

export default function useWebSocket(onMessage: (event: WebSocketEvent) => void, options?: UseWebSocketOptions) {
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const reconnectDelayRef = useRef<number>(1000)
  const intentionalCloseRef = useRef<boolean>(false)
  const onMessageRef = useRef(onMessage)
  const optionsRef = useRef<UseWebSocketOptions | undefined>(options)

  onMessageRef.current = onMessage
  optionsRef.current = options

  const connect = () => {
    const ws = new WebSocket(`ws://${window.location.host}/ws`)
    socketRef.current = ws

    ws.onopen = () => {
      console.info("[WS] Connected")
      reconnectDelayRef.current = 1000
      optionsRef.current?.onOpen?.()
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(event.data) as Record<string, unknown>

        if (parsed.type === "ping" || parsed.event_type === "ping") {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "pong" }))
          }
          return
        }

        onMessageRef.current(parsed as WebSocketEvent)
      } catch (error) {
        console.error("[WS] Failed to parse message", error)
      }
    }

    ws.onclose = (event: CloseEvent) => {
      socketRef.current = null
      optionsRef.current?.onClose?.(event)

      if (intentionalCloseRef.current) {
        return
      }

      if (event.code !== 1000) {
        if (reconnectTimerRef.current !== null) {
          window.clearTimeout(reconnectTimerRef.current)
        }

        const delay = reconnectDelayRef.current
        reconnectTimerRef.current = window.setTimeout(() => {
          connect()
        }, delay)
        reconnectDelayRef.current = Math.min(delay * 2, 30000)
      }
    }

    ws.onerror = (error: Event) => {
      console.error("[WS] Error", error)
      optionsRef.current?.onError?.(error)
    }
  }

  useEffect(() => {
    intentionalCloseRef.current = false
    connect()

    return () => {
      intentionalCloseRef.current = true

      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }

      const ws = socketRef.current
      if (ws && ws.readyState < WebSocket.CLOSING) {
        ws.close(1000)
      }
      socketRef.current = null
    }
    // Intentionally mount-once hook lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

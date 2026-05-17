import React, { useEffect, useRef, useState } from 'react'

type Props = {
  expiry_round: number
  current_round: number
  onExpired?: () => void
  state?: string
}

const SECONDS_PER_ROUND = Number(process.env.REACT_APP_SECONDS_PER_ROUND || 4.5)
const CONFIRMATION_BUFFER_ROUNDS = 10

function formatDisplay(secondsRemaining: number) {
  if (secondsRemaining <= 0) return 'Expired'
  const mins = Math.floor(secondsRemaining / 60)
  const secs = Math.floor(secondsRemaining % 60)
  if (secondsRemaining >= 3600) {
    const hours = Math.floor(secondsRemaining / 3600)
    const rem = secondsRemaining - hours * 3600
    const m = Math.floor(rem / 60)
    return `${hours}h ${m}m`
  }
  return `${mins}m ${secs}s`
}

export default function ExpiryCountdown({ expiry_round, current_round, onExpired, state }: Props) {
  const [seconds, setSeconds] = useState(() => {
    const roundsRemaining = expiry_round - current_round - CONFIRMATION_BUFFER_ROUNDS
    return Math.max(0, Math.floor(roundsRemaining * SECONDS_PER_ROUND))
  })
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    // Recalculate when current_round prop changes
    const roundsRemaining = expiry_round - current_round - CONFIRMATION_BUFFER_ROUNDS
    setSeconds(Math.max(0, Math.floor(roundsRemaining * SECONDS_PER_ROUND)))
  }, [expiry_round, current_round])

  useEffect(() => {
    if (state && (state === 'sold' || state === 'expired')) return
    intervalRef.current = window.setInterval(() => {
      setSeconds((s) => {
        const ns = s - 1
        if (ns <= 0) {
          if (onExpired) onExpired()
          return 0
        }
        return ns
      })
    }, 1000)
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current)
    }
  }, [state, onExpired])

  if (state === 'sold' || state === 'expired') return null

  if (seconds <= 0) {
    return <div className="text-gray-500">Expired</div>
  }

  // urgency classes
  let cls = 'text-green-600'
  if (seconds < 30 * 60) cls = 'text-red-500 animate-pulse'
  else if (seconds < 2 * 3600) cls = 'text-yellow-500'

  if (seconds < 5 * 60) return <div className={cls}>⚠️ Expiring soon</div>

  return <div className={cls}>{formatDisplay(seconds)}</div>
}

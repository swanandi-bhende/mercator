import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../utils/api'
import type { LayoutOutletContext } from '../components/Layout'
import type { TraceEvent } from '../types'

type EventType =
  | 'new_listing'
  | 'payment_confirmed'
  | 'escrow_released'
  | 'reputation_updated'
  | 'new_subscription'
  | 'curator_cycle_complete'
  | 'health_update'
  | 'autonomous_decision'

type ActivityEvent = {
  id: string
  event_type: EventType
  timestamp: string
  payload: Record<string, unknown>
}

const EVENT_TYPES: EventType[] = [
  'new_listing',
  'payment_confirmed',
  'escrow_released',
  'reputation_updated',
  'new_subscription',
  'curator_cycle_complete',
  'health_update',
  'autonomous_decision',
]

function isEventType(value: string): value is EventType {
  return EVENT_TYPES.includes(value as EventType)
}

function toActivityEvent(event: TraceEvent, index: number): ActivityEvent | null {
  if (!isEventType(event.event_type)) return null
  return {
    id: `${event.event_type}-${event.timestamp}-${index}`,
    event_type: event.event_type,
    timestamp: event.timestamp,
    payload: event.payload,
  }
}

function eventColorClass(eventType: EventType) {
  if (eventType === 'escrow_released' || eventType === 'payment_confirmed') return 'activity-live-card--success'
  if (eventType === 'new_listing' || eventType === 'health_update' || eventType === 'reputation_updated') return 'activity-live-card--info'
  if (eventType === 'autonomous_decision') return 'activity-live-card--decision'
  if (eventType === 'new_subscription') return 'activity-live-card--subscription'
  return 'activity-live-card--default'
}

function displayEventType(eventType: EventType) {
  return eventType.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join(' ')
}

function localTime(ts: string) {
  const parsed = new Date(ts)
  if (Number.isNaN(parsed.getTime())) return 'Unknown'
  return parsed.toLocaleTimeString([], { hour12: false })
}

export default function ActivityLedgerPage() {
  const { latestWsEvent } = useOutletContext<LayoutOutletContext>()

  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<EventType | 'all'>('all')
  const [eventCounts, setEventCounts] = useState<Record<string, number>>(() => ({ all: 0 }))

  useEffect(() => {
    let cancelled = false

    const preload = async () => {
      try {
        const response = await api.tracesLatest(20)
        if (cancelled || !response.success) return
        const latestSession = response.sessions?.[0]
        if (!latestSession) return
        const traceResponse = await api.traceSession(latestSession.session_id)
        if (cancelled || !traceResponse.success) return
        const mapped = (traceResponse.events || [])
          .map((event, index) => toActivityEvent(event, index))
          .filter((event): event is ActivityEvent => Boolean(event))
        setEvents(mapped)
      } catch {
        // Leave empty state; websocket stream will populate events.
      }
    }

    void preload()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!latestWsEvent || !isEventType(latestWsEvent.event_type)) return

    const event: ActivityEvent = {
      id: `${latestWsEvent.event_type}-${latestWsEvent.timestamp}-${Date.now()}`,
      event_type: latestWsEvent.event_type,
      timestamp: latestWsEvent.timestamp,
      payload: latestWsEvent.payload,
    }

    setEvents((prev) => [event, ...prev.slice(0, 99)])
    setEventCounts((prev) => ({
      ...prev,
      all: (prev.all || 0) + 1,
      [event.event_type]: (prev[event.event_type] || 0) + 1,
    }))
  }, [latestWsEvent])

  useEffect(() => {
    const baseline: Record<string, number> = { all: events.length }
    for (const eventType of EVENT_TYPES) {
      baseline[eventType] = events.filter((event) => event.event_type === eventType).length
    }
    setEventCounts(baseline)
  }, [events])

  const filteredEvents = useMemo(() => {
    if (activeFilter === 'all') return events
    return events.filter((event) => event.event_type === activeFilter)
  }, [events, activeFilter])

  return (
    <div className="activity-page">
      <section className="activity-hero">
        <div className="home-wrap activity-shell">
          <div className="activity-head-card">
            <p className="home-kicker">Live Activity Ledger</p>
            <h1>Realtime event timeline</h1>
            <p>Historical events are loaded first, then live websocket updates stream in without page refresh.</p>
          </div>

          <div className="activity-filter-bar" role="toolbar" aria-label="Activity event filters">
            <button
              type="button"
              className={`activity-filter-btn ${activeFilter === 'all' ? 'is-active' : ''}`}
              onClick={() => setActiveFilter('all')}
            >
              All <span className="activity-filter-count">{eventCounts.all || 0}</span>
            </button>
            {EVENT_TYPES.map((eventType) => (
              <button
                key={eventType}
                type="button"
                className={`activity-filter-btn ${activeFilter === eventType ? 'is-active' : ''}`}
                onClick={() => setActiveFilter(eventType)}
              >
                {displayEventType(eventType)} <span className="activity-filter-count">{eventCounts[eventType] || 0}</span>
              </button>
            ))}
          </div>

          <div className="activity-live-list">
            {filteredEvents.length === 0 && (
              <article className="activity-live-card activity-live-card--default">
                <h2>No events yet</h2>
                <p>Waiting for live websocket activity.</p>
              </article>
            )}

            {filteredEvents.map((event) => {
              const expanded = expandedId === event.id
              return (
                <article key={event.id} className={`activity-live-card ${eventColorClass(event.event_type)}`}>
                  <button
                    type="button"
                    className="activity-live-card__header"
                    onClick={() => setExpandedId(expanded ? null : event.id)}
                  >
                    <strong>{displayEventType(event.event_type)}</strong>
                    <span>{localTime(event.timestamp)}</span>
                  </button>

                  {expanded && (
                    <dl className="activity-live-details">
                      {Object.entries(event.payload).map(([key, value]) => (
                        <div key={key} className="activity-live-details__row">
                          <dt>{key}</dt>
                          <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </article>
              )
            })}
          </div>
        </div>
      </section>
    </div>
  )
}

import { EmptyState } from '@/components/ui'

import type { ActiveEvents } from '../api'
import { useActiveEvents } from '../hooks'

import { ActiveEventCard } from './ActiveEventCard'
import { QueryResult } from './QueryResult'

function ActiveEventItems({ event_requests: events, message }: ActiveEvents) {
  // The backend sends a message only when no event is active (SCRUM-24 AC11, ADR-0041).
  if (message !== undefined) {
    return <EmptyState message={message} />
  }
  return (
    <ul className="space-y-5">
      {events.map((event) => (
        <li key={event.reference}>
          <ActiveEventCard event={event} />
        </li>
      ))}
    </ul>
  )
}

/** Every active event the backend lists, newest first, each with a way to move it. */
export function ActiveEventList() {
  const active = useActiveEvents()
  return (
    <QueryResult query={active} loadingLabel="Loading active events…">
      {(body) => <ActiveEventItems {...body} />}
    </QueryResult>
  )
}
